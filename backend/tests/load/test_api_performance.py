# backend/tests/load/test_api_performance.py
import asyncio
import aiohttp
import time
from statistics import mean, median

class LoadTestRunner:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    async def make_request(self, session, endpoint):
        start_time = time.time()
        try:
            async with session.get(f"{self.base_url}{endpoint}") as response:
                await response.read()
                end_time = time.time()
                return {
                    'status': response.status,
                    'duration': end_time - start_time,
                    'success': response.status == 200
                }
        except Exception as e:
            return {
                'status': 500,
                'duration': time.time() - start_time,
                'success': False,
                'error': str(e)
            }
    
    async def run_load_test(self, endpoint, concurrent_requests=100, duration_seconds=60):
        print(f"Starting load test: {concurrent_requests} concurrent requests for {duration_seconds}s")
        
        results = []
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < duration_seconds:
                tasks = [
                    self.make_request(session, endpoint) 
                    for _ in range(concurrent_requests)
                ]
                
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                
                # Brief pause between batches
                await asyncio.sleep(0.1)
        
        return self.analyze_results(results)
    
    def analyze_results(self, results):
        successful_requests = [r for r in results if r['success']]
        failed_requests = [r for r in results if not r['success']]
        
        if successful_requests:
            durations = [r['duration'] for r in successful_requests]
            
            analysis = {
                'total_requests': len(results),
                'successful_requests': len(successful_requests),
                'failed_requests': len(failed_requests),
                'success_rate': len(successful_requests) / len(results) * 100,
                'avg_response_time': mean(durations),
                'median_response_time': median(durations),
                'min_response_time': min(durations),
                'max_response_time': max(durations),
                'requests_per_second': len(results) / max(durations) if durations else 0
            }
        else:
            analysis = {
                'total_requests': len(results),
                'successful_requests': 0,
                'failed_requests': len(failed_requests),
                'success_rate': 0,
                'error': 'No successful requests'
            }
        
        return analysis

async def run_performance_tests():
    runner = LoadTestRunner()
    
    endpoints = [
        "/api/v1/air-quality/current",
        "/api/v1/air-quality/predictions/sensor_001",
        "/health"
    ]
    
    for endpoint in endpoints:
        print(f"\n{'='*50}")
        print(f"Testing endpoint: {endpoint}")
        print('='*50)
        
        results = await runner.run_load_test(endpoint, concurrent_requests=50, duration_seconds=30)
        
        print(f"Total requests: {results['total_requests']}")
        print(f"Success rate: {results['success_rate']:.2f}%")
        if 'avg_response_time' in results:
            print(f"Average response time: {results['avg_response_time']:.3f}s")
            print(f"Median response time: {results['median_response_time']:.3f}s")
            print(f"Requests per second: {results['requests_per_second']:.2f}")

if __name__ == "__main__":
    asyncio.run(run_performance_tests())