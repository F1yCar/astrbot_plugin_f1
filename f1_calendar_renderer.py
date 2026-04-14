import json
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1CalendarRenderer:
    """渲染完整赛季赛历图"""

    def __init__(self):
        self.bg_color = (21, 21, 30, 255)
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        self.stripe_color = (29, 29, 39, 255)
        self.dim_color = (150, 150, 150, 255)
        self.green_color = (0, 200, 83, 255)
        self.yellow_color = (255, 200, 0, 255)
        self.sprint_color = (147, 51, 234, 255)

        font_dir = "assets/fonts"
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 20)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 25)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 28)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)
        self.font_time = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 24)

    def _draw_fixed_width_text(self, draw, text, x, y, font, fill, char_width, align="right"):
        """
        逐字符等宽绘制文本（数字、冒号等），每个字符在固定宽度格子内居中。
        align: "right" - x为右边缘; "center" - x为中心; "left" - x为左边缘
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

    def _format_date_range(self, race):
        """获取比赛周末的日期范围字符串"""
        race_date = datetime.strptime(race["date"], "%Y-%m-%d")
        earliest = race_date
        for key in ["FirstPractice", "SprintQualifying", "Sprint", "SecondPractice", "ThirdPractice", "Qualifying"]:
            if key in race:
                d = datetime.strptime(race[key]["date"], "%Y-%m-%d")
                if d < earliest:
                    earliest = d
        return f"{earliest.strftime('%b %d')} - {race_date.strftime('%b %d')}"

    def _is_sprint_weekend(self, race):
        return "Sprint" in race

    def _get_race_status(self, race):
        race_date = datetime.strptime(race["date"], "%Y-%m-%d")
        race_time = datetime.strptime(race.get("time", "00:00:00Z"), "%H:%M:%SZ")
        race_dt = race_date.replace(hour=race_time.hour, minute=race_time.minute, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now > race_dt + timedelta(hours=2):
            return "completed"
        elif now > race_dt - timedelta(days=5):
            return "upcoming"
        else:
            return "future"

    def _utc_to_beijing(self, date_str, time_str):
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%SZ")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_bj = dt_utc + timedelta(hours=8)
        return dt_bj

    def draw_calendar(self, json_path="f1_race_schedule.json"):
        print(">>> [引擎启动] 正在生成完整赛历...")
        if not os.path.exists(json_path):
            print(f"❌ 文件不存在: {json_path}")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        races = data["MRData"]["RaceTable"]["Races"]
        season = data["MRData"]["RaceTable"]["season"]

        num_races = len(races)
        header_h = 220
        row_h = 70
        footer_h = 60
        canvas_w = 1200
        canvas_h = header_h + (num_races * row_h) + footer_h

        canvas = Image.new('RGBA', (canvas_w, canvas_h), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)

        # ── 列布局定义 ──
        col_rd = 80          # 轮次居中
        col_gp = 130         # GP名称左对齐
        col_location = 130   # 地点（在GP名称下方）
        col_date = 680       # 日期范围左对齐
        col_time = 1150      # 正赛时间右对齐

        # ── 1. Header ──
        draw.rectangle([0, 0, canvas_w, 200], fill=(15, 15, 20, 255))
        red_line_x = 210
        draw.text((red_line_x, 55), f"{season} FORMULA 1 SEASON", font=self.font_medium, fill=self.f1_red)
        draw.text((60, 105), "RACE CALENDAR", font=self.font_bold, fill=self.text_color)

        # 列标题
        col_header_y = 185
        draw.text((col_rd, col_header_y), "RD", font=self.font_small, fill=self.dim_color, anchor="mm")
        draw.text((col_gp, col_header_y), "GRAND PRIX", font=self.font_small, fill=self.dim_color, anchor="lm")
        draw.text((col_date, col_header_y), "DATE", font=self.font_small, fill=self.dim_color, anchor="lm")
        draw.text((col_time, col_header_y), "TIME (UTC+8)", font=self.font_small, fill=self.dim_color, anchor="rm")

        # ── 2. 赛程列表 ──
        start_y = header_h
        for i, race in enumerate(races):
            curr_y = start_y + (i * row_h)
            center_y = curr_y + (row_h // 2)

            # 交替行背景
            if i % 2 == 0:
                draw.rectangle([40, curr_y, canvas_w - 40, curr_y + row_h - 4], fill=self.stripe_color)

            round_str = race["round"]
            gp_name = race["raceName"].upper().replace(" GRAND PRIX", " GP")
            locality = race["Circuit"]["Location"]["locality"]
            country = race["Circuit"]["Location"]["country"]
            date_range = self._format_date_range(race)
            is_sprint = self._is_sprint_weekend(race)
            status = self._get_race_status(race)

            # 正赛北京时间
            bj_dt = self._utc_to_beijing(race["date"], race.get("time", "00:00:00Z"))
            race_time_display = bj_dt.strftime("%H:%M")

            # 状态颜色
            if status == "completed":
                round_color = self.dim_color
                name_color = self.dim_color
                loc_color = (100, 100, 100, 255)
                date_color = self.dim_color
                time_color = self.dim_color
            elif status == "upcoming":
                round_color = self.green_color
                name_color = self.text_color
                loc_color = self.dim_color
                date_color = self.text_color
                time_color = self.yellow_color
            else:
                round_color = self.f1_red
                name_color = self.text_color
                loc_color = self.dim_color
                date_color = self.text_color
                time_color = self.yellow_color

            # 状态指示条（即将到来的比赛）
            if status == "upcoming":
                draw.rectangle([40, curr_y, 46, curr_y + row_h - 4], fill=self.green_color)

            # 轮次（等宽渲染）
            self._draw_fixed_width_text(draw, round_str, col_rd, center_y, self.font_medium, round_color, char_width=20, align="center")

            # 大奖赛名称
            draw.text((col_gp, center_y - 8), gp_name, font=self.font_medium, fill=name_color, anchor="lm")

            # 冲刺赛标记
            if is_sprint:
                gp_bbox = draw.textbbox((col_gp, center_y - 8), gp_name, font=self.font_medium, anchor="lm")
                tag_x = gp_bbox[2] + 10
                tag_font = ImageFont.truetype("assets/fonts/Formula1-Regular.ttf", 13)
                draw.rounded_rectangle([tag_x, center_y - 19, tag_x + 55, center_y - 4], radius=3, fill=self.sprint_color)
                draw.text((tag_x + 27, center_y - 12), "SPRINT", font=tag_font, fill=self.text_color, anchor="mm")

            # 地点（小字，GP名称下方）
            location_str = f"{locality}, {country}"
            draw.text((col_location, center_y + 14), location_str, font=self.font_small, fill=loc_color, anchor="lm")

            # 日期范围
            draw.text((col_date, center_y - 6), date_range, font=self.font_small, fill=date_color, anchor="lm")

            # 正赛日期
            race_date_str = bj_dt.strftime("%a").upper()
            draw.text((col_date, center_y + 16), race_date_str, font=self.font_small, fill=loc_color, anchor="lm")

            # 正赛时间（等宽渲染，确保 HH:MM 对齐）
            self._draw_fixed_width_text(draw, race_time_display, col_time, center_y, self.font_time, time_color, char_width=18, align="right")

        # ── 3. Footer ──
        draw.rectangle([0, canvas_h - footer_h, canvas_w, canvas_h], fill=self.f1_red)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        draw.text((20, canvas_h - footer_h + 18), f"@F1y/Car | TIMES IN UTC+8 | RENDERED: {current_time}", font=self.font_small, fill=self.text_color)

        # ── 4. 叠加 F1 Logo ──
        apply_f1_logo(canvas, max_width_ratio=0.10, margin=(24, 52), opacity=235, position="top-left")

        canvas.save("race_calendar.png")
        print("🏁 完整赛历渲染完成！")


if __name__ == "__main__":
    F1CalendarRenderer().draw_calendar()
