# file: test_python_tasks.py
# Python 3.8+
import threading
import queue
import time
import math
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

TASK_QUEUE_SIZE = 16
NUM_WORKERS = 6
NUM_TASKS = 40
TIMEOUT_PER_TASK = 5.0  # seconds

def is_probable_prime(n: int) -> bool:
    """Rabin-Miller (simple rounds) — probabilistic primality"""
    if n < 2:
        return False
    small_primes = [2,3,5,7,11,13,17,19,23,29]
    for p in small_primes:
        if n % p == 0:
            return n == p
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    # a few bases
    for a in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True

def partial_factor(n: int, limit=100_000):
    """Try to find a small factor up to limit (trial division with step)"""
    i = 2
    while i*i <= n and i <= limit:
        if n % i == 0:
            return i, n//i
        i += 1 if i == 2 else 2
    return None

def worker_task(n):
    start = time.time()
    prime = is_probable_prime(n)
    factor_result = None if prime else partial_factor(n, limit=200_000)
    duration = time.time() - start
    return {"n": n, "prime": prime, "factor": factor_result, "time": duration}

def produce_tasks(q: queue.Queue, count: int):
    for i in range(count):
        # generate some large-ish odd numbers (50..60 bits)
        n = random.getrandbits(random.randint(40, 56)) | 1
        q.put(n)
    # signal end
    for _ in range(NUM_WORKERS):
        q.put(None)

def consumer_loop(q: queue.Queue, out_list: list, idx: int):
    while True:
        n = q.get()
        if n is None:
            q.task_done()
            break
        try:
            res = worker_task(n)
            out_list.append((idx, res))
        except Exception as e:
            out_list.append((idx, {"n": n, "error": str(e)}))
        finally:
            q.task_done()

def run_pool():
    q = queue.Queue(maxsize=TASK_QUEUE_SIZE)
    results = []
    producer = threading.Thread(target=produce_tasks, args=(q, NUM_TASKS), daemon=True)
    consumers = [threading.Thread(target=consumer_loop, args=(q, results, i), daemon=True)
                 for i in range(NUM_WORKERS)]

    t0 = time.time()
    for c in consumers:
        c.start()
    producer.start()

    # optionally wait with timeout for queue to drain
    q.join()
    ttotal = time.time() - t0
    print(f"All tasks finished in {ttotal:.2f}s; results collected: {len(results)}")
    # sort and show some samples
    results_sorted = sorted(results, key=lambda x: x[1].get("time", 0), reverse=True)
    print("Top 5 slowest tasks:")
    for idx, r in results_sorted[:5]:
        print(f" worker {idx} - n={r['n']:,} prime={r.get('prime')} time={r.get('time'):.3f}s factor={r.get('factor')}")

if __name__ == "__main__":
    random.seed(42)
    run_pool()
