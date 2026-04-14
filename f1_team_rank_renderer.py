import json
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1TeamRankRenderer:
    def __init__(self):
        self.bg_color = (21, 21, 30, 255)
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        self.stripe_color = (29, 29, 39, 255)
        
        font_dir = "assets/fonts"
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 25)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 35)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)

    def _draw_fixed_width_number(self, draw, text, x, y, font, fill, char_width, align="right", narrow_chars=None, narrow_width=None):
        """
        逐字符等宽绘制数字，每个字符在固定宽度的格子内居中。
        align: "right" - x 为右边缘; "center" - x 为中心点; "left" - x 为左边缘
        narrow_chars: 需要使用窄宽度的字符集合 (如 ".:")
        narrow_width: 窄字符的宽度
        """
        if narrow_chars is None:
            narrow_chars = set()
        if narrow_width is None:
            narrow_width = char_width

        # 计算总宽度（考虑窄字符）
        total_width = sum(narrow_width if ch in narrow_chars else char_width for ch in text)
        if align == "right":
            start_x = x - total_width
        elif align == "center":
            start_x = x - total_width / 2
        else:
            start_x = x

        cursor = start_x
        for ch in text:
            w = narrow_width if ch in narrow_chars else char_width
            cx = cursor + w / 2
            draw.text((cx, y), ch, font=font, fill=fill, anchor="mm")
            cursor += w

    def draw_team_rank(self, json_path="f1_driver_standings.json"):
        print(">>> [引擎启动] 正在聚合并生成车队榜 (原生排版引擎)...")
        if not os.path.exists(json_path): return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        drivers = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
        season = data["MRData"]["StandingsTable"]["season"]
        round_num = data["MRData"]["StandingsTable"]["round"]
        
        team_data = {}
        for d in drivers:
            t_name = d["Constructors"][0]["name"]
            pts = float(d["points"])
            if t_name not in team_data:
                team_data[t_name] = 0
            team_data[t_name] += pts
        
        sorted_teams = sorted(team_data.items(), key=lambda x: x[1], reverse=True)

        num_teams = len(sorted_teams)
        header_h = 220
        row_h = 90
        footer_h = 60
        canvas_h = header_h + (num_teams * row_h) + footer_h

        canvas = Image.new('RGBA', (1200, canvas_h), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)

        # 1. 顶部 Header
        draw.rectangle([0, 0, 1200, 200], fill=(15, 15, 20, 255))
        draw.text((60, 60), f"{season} FORMULA 1 SEASON", font=self.font_regular, fill=self.f1_red)
        draw.text((60, 110), f"CONSTRUCTOR STANDINGS - ROUND {round_num}", font=self.font_bold, fill=self.text_color)
        
        draw.text((100, 180), "POS", font=self.font_small, fill=(150, 150, 150, 255), anchor="mm")
        draw.text((180, 180), "TEAM", font=self.font_small, fill=(150, 150, 150, 255), anchor="lm")
        draw.text((1140, 180), "PTS", font=self.font_small, fill=(150, 150, 150, 255), anchor="rm")

        # 2. 列表动态渲染
        start_y = header_h
        for i, (name, pts) in enumerate(sorted_teams):
            curr_y = start_y + (i * row_h)
            center_y = curr_y + (row_h // 2)
            
            if i % 2 == 0:
                draw.rectangle([40, curr_y, 1160, curr_y + row_h - 6], fill=self.stripe_color)
            
            pts_str = str(int(pts)) if pts % 1 == 0 else str(pts)
            pos_str = str(i+1)

            # 排名：等宽居中绘制 | 积分：等宽右对齐绘制 | 车队名正常渲染
            # char_width=32 紧凑间距，Bold 45 最宽字形 "0" 约 28px，32px 留 4px 呼吸感
            self._draw_fixed_width_number(draw, pos_str, 100, center_y, self.font_medium, self.f1_red, char_width=32, align="center")
            draw.text((180, center_y), name.upper(), font=self.font_medium, fill=self.text_color, anchor="lm")
            self._draw_fixed_width_number(draw, pts_str, 1140, center_y, self.font_medium, self.text_color, char_width=32, align="right", narrow_chars={"."}, narrow_width=18)

        # 3. 底部落款
        draw.rectangle([0, canvas_h - footer_h, 1200, canvas_h], fill=self.f1_red)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        draw.text((20, canvas_h - footer_h + 18), f"@F1y/Car | RENDERED: {current_time}", font=self.font_small, fill=self.text_color)

        # 4. 叠加 F1 Logo
        apply_f1_logo(canvas, max_width_ratio=0.09, margin=(24, 10), opacity=235, position="top-left")

        canvas.save("team_rankings.png")
        print(f"🏁 车队榜渲染完成！")

if __name__ == "__main__":
    F1TeamRankRenderer().draw_team_rank()