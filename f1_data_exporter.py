import aiohttp
import asyncio
import feedparser
import json
import os
from datetime import datetime

class F1DataExporter:
    def __init__(self):
        self.api_base = "https://api.jolpi.ca/ergast/f1"
        self.rss_url = "https://www.autosport.com/rss/f1/news/"
        
    async def fetch_json(self, endpoint):
        """异步拉取 API 原始 JSON 数据"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_base}{endpoint}", timeout=15) as response:
                if response.status == 200:
                    return await response.json()
        return {"error": "Telemetry lost", "status": "failed"}

    def save_json(self, filename, data):
        """将数据格式化并写入本地 JSON 文件"""
        filepath = os.path.join(os.getcwd(), filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ Data exported: {filename}")

    async def export_standings(self):
        """拉取并保存完整车手排行"""
        print(">>> 拉取当前车手积分榜...")
        data = await self.fetch_json("/current/driverStandings.json")
        self.save_json("f1_driver_standings.json", data)

    async def export_schedule(self):
        """拉取并保存完整赛季赛程（含一练、二练、三练、排位时间）"""
        print(">>> 拉取全赛季赛历与时间表...")
        data = await self.fetch_json("/current.json")
        self.save_json("f1_race_schedule.json", data)

    def export_paddock_news(self):
        """抓取围场新闻并转存为 JSON"""
        print(">>> 抓取围场最新资讯...")
        feed = feedparser.parse(self.rss_url)
        news_data = {
            "update_time": datetime.now().isoformat(),
            "source": "Autosport RSS",
            "articles": []
        }
        for entry in feed.entries[:10]: # 保存前10条
            news_data["articles"].append({
                "title": entry.title,
                "published": getattr(entry, 'published', 'N/A'),
                "link": entry.link,
                "summary": getattr(entry, 'summary', '')
            })
        self.save_json("f1_paddock_news.json", news_data)

    def export_visual_assets_template(self):
        """生成静态图像资产的 JSON 模板"""
        print(">>> 生成视觉资产 JSON 模板...")
        template_data = {
            "_instruction": "此文件用于存储不变的视觉资产链接，请手动填入 F1 官网抓取的图片 URL",
            "teams": {
                "red_bull": {
                    "name": "Red Bull Racing",
                    "car_url": "YOUR_IMAGE_URL_HERE",
                    "logo_url": "YOUR_IMAGE_URL_HERE"
                },
                "ferrari": {
                    "name": "Scuderia Ferrari",
                    "car_url": "YOUR_IMAGE_URL_HERE",
                    "logo_url": "YOUR_IMAGE_URL_HERE"
                }
            },
            "drivers": {
                "verstappen": {
                    "name": "Max Verstappen",
                    "headshot_url": "YOUR_IMAGE_URL_HERE",
                    "number": 1
                },
                "leclerc": {
                    "name": "Charles Leclerc",
                    "headshot_url": "YOUR_IMAGE_URL_HERE",
                    "number": 16
                }
            }
        }
        self.save_json("f1_visual_assets.json", template_data)

async def run_pipeline():
    print("🔧 F1 Data Export Pipeline Initializing...\n" + "="*45)
    exporter = F1DataExporter()
    
    # 并发执行拉取任务以提高效率
    await asyncio.gather(
        exporter.export_standings(),
        exporter.export_schedule()
    )
    
    # 同步执行新闻抓取和模板生成
    exporter.export_paddock_news()
    exporter.export_visual_assets_template()
    
    print("="*45 + "\n🏁 All telemetry data successfully dumped to local directory.")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
    print("\n" + "="*45)
    input("Box box. 导出完毕，按 Enter 键关闭终端进程...")