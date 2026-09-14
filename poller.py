import os, sys, json, time, traceback, requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')
PRODUCT_ID = os.environ.get('PRODUCT_ID')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not PRODUCT_ID:
    raise RuntimeError('Missing required env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY, PRODUCT_ID')

REST_URL = f"{SUPABASE_URL}/rest/v1"
SB_HEADERS = {
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "apikey": SUPABASE_SERVICE_KEY,
    "Content-Type": "application/json",
}

REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 5


def request_with_retry(method, url, **kwargs):
    """Issue a request, retrying transient 5xx and network failures.

    Supabase intermittently answers 522 while a project is waking up. Retrying
    keeps the poll cycle alive instead of aborting it with a traceback.
    Returns the response, or None once every attempt has been used up.
    """
    kwargs.setdefault('timeout', REQUEST_TIMEOUT)
    reason = 'no response'
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            reason = type(exc).__name__
        else:
            if resp.status_code < 500:
                return resp
            reason = 'HTTP %s' % resp.status_code
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    print('Retrying next cycle: %s %s unreachable (%s)' % (method, url, reason), flush=True)
    return None


def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def upload_file(bucket, file_path, content):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.post(url, headers={
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/octet-stream",
        "x-upsert": "true",
    }, data=content, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def insert_notification(customer_id, title, body, notification_type):
    url = f"{REST_URL}/notifications"
    payload = {
        "product_id": PRODUCT_ID,
        "customer_id": customer_id,
        "title": title,
        "body": body,
        "type": notification_type,
        "read": False,
    }
    resp = requests.post(url, headers=SB_HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()


def update_job(job_id, payload):
    url = f"{REST_URL}/jobs?id=eq.{job_id}"
    headers = {**SB_HEADERS, "Prefer": "return=minimal"}
    resp = requests.patch(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()


def poll():
    print("Poller started", flush=True)
    import processor
    while True:
        try:
            url = f"{REST_URL}/jobs?status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}&order=created_at.asc&limit=1"
            resp = request_with_retry("GET", url, headers=SB_HEADERS)
            if resp is None:
                time.sleep(60)
                continue
            resp.raise_for_status()
            jobs = resp.json()
            if not jobs:
                time.sleep(60)
                continue
            job = jobs[0]
            job_id = job.get('id')
            customer_id = job.get('customer_id')
            input_file_path = job.get('input_file_path')
            print(f"Processing job {job_id} for customer {customer_id}", flush=True)
            try:
                file_bytes = download_file('uploads', input_file_path)
                results = processor.process_file(file_bytes)
                if not isinstance(results, list):
                    results = [results]
                for r in results:
                    record = {
                        "product_id": PRODUCT_ID,
                        "customer_id": customer_id,
                        "title": r["title"],
                        "status": r["status"],
                        "details": r["details"],
                        "source_file_path": input_file_path,
                        "due_date": r.get("due_date"),
                    }
                    rec_resp = request_with_retry(
                        "POST",
                        f"{REST_URL}/records",
                        headers={**SB_HEADERS, "Prefer": "return=minimal"},
                        json=record,
                    )
                    if rec_resp is None:
                        raise RuntimeError('insert into records failed after retries')
                    rec_resp.raise_for_status()
                output_file_path = f"results/{PRODUCT_ID}/{job_id}.json"
                upload_file('results', output_file_path, json.dumps(results).encode('utf-8'))
                summary = f"Extracted {len(results)} records"
                update_job(job_id, {
                    "status": "completed",
                    "output_file_path": output_file_path,
                    "result_summary": summary,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                try:
                    insert_notification(
                        customer_id,
                        "Processing complete",
                        "Your upload has been processed successfully.",
                        "success",
                    )
                except Exception:
                    traceback.print_exc()
            except Exception as e:
                traceback.print_exc()
                error_summary = str(e)[:1000]
                try:
                    update_job(job_id, {
                        "status": "failed",
                        "result_summary": error_summary,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    insert_notification(
                        customer_id,
                        "Processing failed",
                        "There was an error processing your upload.",
                        "error",
                    )
                except Exception as inner:
                    traceback.print_exc()
            time.sleep(60)
        except Exception as e:
            traceback.print_exc()
            time.sleep(60)


if __name__ == "__main__":
    print("Poller started")
    poll()
