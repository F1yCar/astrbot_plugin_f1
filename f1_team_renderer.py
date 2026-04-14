import json
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1TeamRenderer:
    def __init__(self):
        # 赛道环境设置
        self.bg_color = (21, 21, 30, 255) 
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        
        # 挂载动力单元
        font_dir = "assets/fonts"
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 18)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 26)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 70)
        
        # 加载本地视觉映射表
        with open("f1_local_assets.json", "r", encoding="utf-8") as f:
            self.assets = json.load(f)
            
        self.team_standings = {}
        self._load_standings_data("f1_driver_standings.json")

    def _match_team_id(self, api_id):
        mapping = {
            "red_bull": "redbullracing",
            "rb": "racingbulls",
            "aston_martin": "astonmartin",
        }
        return mapping.get(api_id, api_id)

    def _load_standings_data(self, filepath):
        if not os.path.exists(filepath): return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            driver_list = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
            team_calc = {}
            for item in driver_list:
                pts = float(item["points"])
                wins = int(item.get("wins", 0))
                d_code = item["Driver"].get("code", "N/A")
                c_api_id = item["Constructors"][0]["constructorId"].lower()
                t_local_id = self._match_team_id(c_api_id)
                if t_local_id not in team_calc:
                    team_calc[t_local_id] = {"points": 0, "wins": 0, "drivers": []}
                team_calc[t_local_id]["points"] += pts
                team_calc[t_local_id]["wins"] += wins
                team_calc[t_local_id]["drivers"].append(d_code)
            sorted_teams = sorted(team_calc.items(), key=lambda x: x[1]["points"], reverse=True)
            for rank, (t_id, t_data) in enumerate(sorted_teams, start=1):
                self.team_standings[t_id] = {
                    "points": t_data["points"], "wins": t_data["wins"],
                    "position": rank, "drivers": t_data["drivers"]
                }
        except Exception as e: print(f"API Error: {e}")

    def draw_team_card(self, team_id="mercedes"):
        """硬核对齐版：Logo+车队名视为纵向整体，车手名与其中心线水平对齐"""
        print(f">>>> 正在执行纵向中轴线精密渲染 {team_id}...")
        
        team_data = self.assets["teams"].get(team_id)
        if not team_data: return

        stats = self.team_standings.get(team_id, {"points": 0, "wins": 0, "position": "-", "drivers": []})
        canvas = Image.new('RGBA', (1200, 480), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)

        # 1. 赛车背景：居中沉底
        if "local_car_right_path" in team_data and os.path.exists(team_data["local_car_right_path"]):
            car_img = Image.open(team_data["local_car_right_path"]).convert("RGBA")
            target_width = 1100
            scale_ratio = target_width / car_img.width
            target_height = int(car_img.height * scale_ratio)
            car_img = car_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            r, g, b, a = car_img.split()
            a = a.point(lambda p: int(p * 0.15)) 
            car_img = Image.merge('RGBA', (r, g, b, a))
            canvas.paste(car_img, ((1200 - target_width) // 2, 455 - target_height), car_img)

        # 2. 左侧整体块 (Logo + 车队名) 坐标预设
        margin = 80
        logo_top_y = 40
        logo_h = 70
        
        # 渲染 Logo
        logo_w = 0
        if "local_logo_path" in team_data and os.path.exists(team_data["local_logo_path"]):
            logo_img = Image.open(team_data["local_logo_path"]).convert("RGBA")
            logo_w = int(logo_h * logo_img.width / logo_img.height)
            logo_img = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            canvas.paste(logo_img, (margin, logo_top_y), logo_img)
        
        # 渲染车队名 (紧贴 Logo 下方)
        team_name_y = 120
        draw.text((margin, team_name_y), team_data["name"].upper(), font=self.font_small, fill=(180, 180, 180, 255))
        
        # 【关键计算】：计算左侧整体的高度范围
        # 整体顶部是 logo_top_y (40)，底部是车队名文本的底部
        name_bbox = draw.textbbox((margin, team_name_y), team_data["name"].upper(), font=self.font_small)
        block_bottom_y = name_bbox[3]
        
        # 计算左侧整体的垂直中心点 (Central Axis)
        v_center_y = (logo_top_y + block_bottom_y) / 2
        
        # 计算左侧整体的右边缘
        block_right_edge = max(margin + logo_w, name_bbox[2])

        # 3. 车手缩写：水平中心点对齐 v_center_y
        drivers = stats["drivers"]
        if len(drivers) == 2:
            right_limit = 1200 - margin
            d1_code, d2_code = drivers[0], drivers[1]
            
            # 车手 2：右边缘对齐 1120，纵向锚定 mm (Middle)
            draw.text((right_limit, v_center_y), d2_code, font=self.font_bold, fill=self.text_color, anchor="rm")
            
            # 获取车手 2 的左边缘坐标
            d2_bbox = draw.textbbox((right_limit, v_center_y), d2_code, font=self.font_bold, anchor="rm")
            d2_left_edge = d2_bbox[0]
            
            # 车手 1：放在左侧块右边缘和车手 2 左边缘的中点，纵向锚定 mm
            d1_center_x = (block_right_edge + d2_left_edge) / 2
            draw.text((d1_center_x, v_center_y), d1_code, font=self.font_bold, fill=self.text_color, anchor="mm")

        # 4. 下方数据展示 (RANK | POINTS | WINS)
        draw.text((margin, 230), "RANK", font=self.font_small, fill=(150, 150, 150, 255))
        draw.text((margin, 260), f"P{stats['position']}", font=self.font_bold, fill=self.text_color)
        
        draw.text((480, 230), "POINTS", font=self.font_small, fill=(150, 150, 150, 255))
        pts_fmt = int(stats['points']) if stats['points'] % 1 == 0 else stats['points']
        draw.text((480, 260), f"{pts_fmt}", font=self.font_bold, fill=self.f1_red)
        
        draw.text((880, 230), "WINS", font=self.font_small, fill=(150, 150, 150, 255))
        draw.text((880, 260), f"{stats['wins']}", font=self.font_bold, fill=(255, 215, 0, 255))

        # 5. 红线水印
        draw.polygon([(0, 480), (1200, 480), (1200, 455), (0, 455)], fill=self.f1_red)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((20, 458), f"@F1y/Car | {current_time}", font=self.font_small, fill=(255, 255, 255, 180))

        # 6. 叠加 F1 Logo
        apply_f1_logo(canvas, max_width_ratio=0.12, margin=(24, 80), opacity=240, position="bottom-left")

        output_path = f"team_banner_{team_id}.png"
        canvas.save(output_path)
        print(f"🏁 渲染完成！车手名已与左侧整体纵向对齐。")

if __name__ == "__main__":
    renderer = F1TeamRenderer()
    renderer.draw_team_card(team_id="mercedes")
    renderer.draw_team_card(team_id="redbullracing")