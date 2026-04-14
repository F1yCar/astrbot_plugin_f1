import json
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1DriverRankRenderer:
    def __init__(self):
        self.bg_color = (21, 21, 30, 255)
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        self.stripe_color = (29, 29, 39, 255) 
        
        font_dir = "assets/fonts"
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 20)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 25)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 35)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45) 

    def _draw_fixed_width_number(self, draw, text, x, y, font, fill, char_width, align="right"):
        """
        逐字符等宽绘制数字，每个字符在固定宽度的格子内居中。
        align: "right" - x 为右边缘; "center" - x 为中心点; "left" - x 为左边缘
        """
        total_width = len(text) * char_width
        if align == "right":
            start_x = x - total_width
        elif align == "center":
            start_x = x - total_width / 2
        else:
            start_x = x

        for i, ch in enumerate(text):
            cx = start_x + i * char_width + char_width / 2
            draw.text((cx, y), ch, font=font, fill=fill, anchor="mm")

    def draw_rank_card(self, json_path="f1_driver_standings.json"):
        print(">>> [引擎启动] 正在生成车手积分榜 (原生排版引擎)...")
        if not os.path.exists(json_path): return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        standings = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
        season = data["MRData"]["StandingsTable"]["season"]
        round_num = data["MRData"]["StandingsTable"]["round"]

        num_drivers = len(standings)
        header_h = 220
        row_h = 65
        footer_h = 60
        canvas_h = header_h + (num_drivers * row_h) + footer_h

        canvas = Image.new('RGBA', (1200, canvas_h), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)

        # 1. 顶部 Header
        draw.rectangle([0, 0, 1200, 200], fill=(15, 15, 20, 255))
        red_line_x = 210
        draw.text((red_line_x, 60), f"{season} FORMULA 1 SEASON", font=self.font_medium, fill=self.f1_red)
        draw.text((60, 110), f"DRIVER STANDINGS - ROUND {round_num}", font=self.font_bold, fill=self.text_color)

        draw.text((100, 180), "POS", font=self.font_small, fill=(150, 150, 150, 255), anchor="mm")
        draw.text((160, 180), "DRIVER", font=self.font_small, fill=(150, 150, 150, 255), anchor="lm")
        draw.text((1140, 180), "PTS", font=self.font_small, fill=(150, 150, 150, 255), anchor="rm")

        # 2. 列表动态渲染
        start_y = header_h
        for i, item in enumerate(standings): 
            curr_y = start_y + (i * row_h)
            center_y = curr_y + (row_h // 2)
            
            if i % 2 == 0:
                draw.rectangle([40, curr_y, 1160, curr_y + row_h - 4], fill=self.stripe_color)

            pos_str = str(item["position"])
            code = item["Driver"].get("code", "N/A")
            name = f"{item['Driver']['givenName']} {item['Driver']['familyName']}".upper()
            pts_float = float(item["points"])
            pts_str = str(int(pts_float)) if pts_float % 1 == 0 else str(pts_float)
            team = item["Constructors"][0]["name"].upper()

            # 排名：等宽居中绘制 | 积分：等宽右对齐绘制 | 其余正常渲染
            # char_width=24 紧凑间距，适配 Bold 35 字形
            self._draw_fixed_width_number(draw, pos_str, 100, center_y, self.font_medium, self.f1_red, char_width=24, align="center")
            draw.text((160, center_y), code, font=self.font_medium, fill=self.text_color, anchor="lm")
            draw.text((280, center_y), name, font=self.font_regular, fill=self.text_color, anchor="lm")
            draw.text((750, center_y), team, font=self.font_small, fill=(150, 150, 150, 255), anchor="lm")
            self._draw_fixed_width_number(draw, pts_str, 1140, center_y, self.font_medium, self.text_color, char_width=24, align="right")

        # 3. 底部落款
        draw.rectangle([0, canvas_h - footer_h, 1200, canvas_h], fill=self.f1_red)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        draw.text((20, canvas_h - footer_h + 18), f"@F1y/Car | RENDERED: {current_time}", font=self.font_small, fill=self.text_color)

        # 4. 叠加 F1 Logo
        apply_f1_logo(canvas, max_width_ratio=0.10, margin=(24, 56), opacity=235, position="top-left")

        canvas.save("driver_rankings.png")
        print(f"🏁 车手榜渲染完成！")

if __name__ == "__main__":
    F1DriverRankRenderer().draw_rank_card()