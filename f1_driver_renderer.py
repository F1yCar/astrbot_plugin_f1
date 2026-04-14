import json
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1Renderer:
    def __init__(self):
        # 赛道环境设置
        self.bg_color = (21, 21, 30, 255) 
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        
        # 挂载多级动力单元 (字体库)
        font_dir = "assets/fonts"
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 20)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 35)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 70)
        
        # 1. 加载本地视觉映射表
        with open("f1_local_assets.json", "r", encoding="utf-8") as f:
            self.assets = json.load(f)
            
        # 2. 挂载 API 实时积分遥测数据
        self.standings = {}
        self._load_standings_data("f1_driver_standings.json")

    def _load_standings_data(self, filepath):
        """解析 API JSON 并自动匹配本地 ID"""
        if not os.path.exists(filepath):
            print(f"  [!] 警告: 未找到积分榜遥测文件 {filepath}")
            return
            
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        try:
            # 剥离 JSON 嵌套外壳，直达核心数据组
            driver_list = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
            
            for item in driver_list:
                api_id = item["Driver"]["driverId"].lower() # 例如 max_verstappen
                pts = item["points"]
                pos = item["position"]
                
                # 模糊匹配引擎：对齐 API ID 和 Local ID
                for local_id in self.assets["drivers"].keys():
                    if local_id in api_id or api_id in local_id:
                        self.standings[local_id] = {
                            "points": pts,
                            "position": pos
                        }
                        break
            print("  [>] API 积分榜遥测数据已成功注入。")
        except Exception as e:
            print(f"  [!] API 数据解析失败，请检查 JSON 结构: {e}")

    def draw_test_driver_card(self, driver_id="verstappen", team_id="redbullracing"):
        """单圈渲染测试：数据驱动版 4:3 车手卡片"""
        print(f">>> 正在渲染 {driver_id} 的数据驱动卡片...")
        
        driver_data = self.assets["drivers"].get(driver_id)
        team_data = self.assets["teams"].get(team_id)
        
        if not driver_data or not team_data:
            print("❌ 视觉资产缺失，无法渲染")
            return
            
        # 从字典提取实时数据，若无数据则返回横线
        stats = self.standings.get(driver_id, {"points": "-", "position": "-"})
        current_points = stats["points"]
        current_position = stats["position"]
            
        # 1. 创建底盘 (1440x1080)
        canvas = Image.new('RGBA', (1440, 1080), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)
        
        # 2. 喷涂背景装饰 (红线)
        draw.polygon([(0, 1080), (1440, 1080), (1440, 1050), (0, 1050)], fill=self.f1_red)

        # 3. 安装白色车号水印
        if "local_number_path" in driver_data and os.path.exists(driver_data["local_number_path"]):
            num_img = Image.open(driver_data["local_number_path"]).convert("RGBA")
            new_num_height = 850
            new_num_width = int(new_num_height * num_img.width / num_img.height)
            num_img = num_img.resize((new_num_width, new_num_height), Image.Resampling.LANCZOS)
            
            r, g, b, a = num_img.split()
            a = a.point(lambda p: int(p * 0.15)) 
            num_img = Image.merge('RGBA', (r, g, b, a))
            
            paste_x = 1440 - new_num_width - 150 
            paste_y = (1080 - new_num_height) // 2
            canvas.paste(num_img, (paste_x, paste_y), num_img)

        # 4. 安装车手定妆照
        if "local_path" in driver_data and os.path.exists(driver_data["local_path"]):
            driver_img = Image.open(driver_data["local_path"]).convert("RGBA")
            
            crop_box = (0, 0, driver_img.width, int(driver_img.height * 0.40))
            driver_img = driver_img.crop(crop_box)
            
            target_height = 1000 
            scale_ratio = target_height / driver_img.height
            new_width = int(driver_img.width * scale_ratio)
            
            driver_img = driver_img.resize((new_width, target_height), Image.Resampling.LANCZOS)
            
            paste_x = 1440 - new_width
            paste_y = 1080 - target_height
            canvas.paste(driver_img, (paste_x, paste_y), driver_img)
            
        # 5. 车队 Logo
        if "local_logo_path" in team_data and os.path.exists(team_data["local_logo_path"]):
            logo_img = Image.open(team_data["local_logo_path"]).convert("RGBA")
            logo_img = logo_img.resize((200, int(200 * logo_img.height / logo_img.width)))
            canvas.paste(logo_img, (80, 80), logo_img)

        # 6. 打印核心遥测数据 (左侧动态排版)
        last_name = driver_data["name"].split(" ")[-1].upper()
        first_name = driver_data["name"].split(" ")[0].upper()
        
        # 动态渲染 API 数据
        draw.text((80, 610), f"P{current_position}", font=self.font_bold, fill=self.text_color)
        draw.text((80, 680), f"{current_points} PTS", font=self.font_medium, fill=self.f1_red)
        
        # 姓名与车队
        draw.text((80, 760), first_name, font=self.font_regular, fill=self.text_color)
        draw.text((80, 810), last_name, font=self.font_bold, fill=self.text_color)
        draw.text((80, 920), team_data["name"].upper(), font=self.font_regular, fill=(180, 180, 180, 255))

        # 7. 防伪水印
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        watermark_text = f"@F1y/Car | RENDERED: {current_time}"
        draw.text((20, 1055), watermark_text, font=self.font_small, fill=(255, 255, 255, 180))

        # 8. 叠加 F1 Logo
        apply_f1_logo(canvas, max_width_ratio=0.14, margin=(80, 120), opacity=236, position="top-right")

        output_path = "test_driver_card_4x3.png"
        canvas.save(output_path)
        print(f"🏁 渲染完成！已输出至 {output_path}")

if __name__ == "__main__":
    renderer = F1Renderer()
    # 测试安东内利 (查看模糊匹配和排名是否正确加载)
    renderer.draw_test_driver_card(driver_id="antonelli", team_id="mercedes")