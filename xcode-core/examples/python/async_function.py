"""异步函数 trace 示例"""
import asyncio


async def fetch_data(url: str) -> dict:
    await asyncio.sleep(0.1)
    return {"url": url, "data": "..."}


async def process_pipeline(items: list) -> list:
    results = []
    for item in items:
        result = await fetch_data(item)
        results.append(result)
    return results


if __name__ == '__main__':
    items = ["http://a.com", "http://b.com"]
    results = asyncio.run(process_pipeline(items))
    print(f"Processed {len(results)} items")
