import json
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
from f1_logo_utils import apply_f1_logo

class F1RaceDetailRenderer:
    """渲染单场大奖赛的详细赛程时间表"""

    def __init__(self):
        self.bg_color = (21, 21, 30, 255)
        self.text_color = (255, 255, 255, 255)
        self.f1_red = (225, 6, 0, 255)
        self.stripe_color = (29, 29, 39, 255)
        self.dim_color = (150, 150, 150, 255)
        self.green_color = (0, 200, 83, 255)
        self.yellow_color = (255, 200, 0, 255)
        self.sprint_color = (147, 51, 234, 255)
        self.accent_blue = (0, 144, 255, 255)

        font_dir = "assets/fonts"
        self.font_tiny = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 16)
        self.font_small = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 20)
        self.font_regular = ImageFont.truetype(f"{font_dir}/Formula1-Regular.ttf", 25)
        self.font_medium = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 28)
        self.font_large = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 36)
        self.font_bold = ImageFont.truetype(f"{font_dir}/Formula1-Bold.ttf", 45)

    def _draw_fixed_width_text(self, draw, text, x, y, font, fill, char_width, align="right", narrow_chars=None, narrow_width=None):
        """逐字符等宽绘制，确保数字列对齐。narrow_chars/narrow_width 用于窄字符（如冒号）单独收窄"""
        if narrow_chars is None:
            narrow_chars = set()
        if narrow_width is None:
            narrow_width = char_width

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

    def _utc_to_beijing(self, date_str, time_str):
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%SZ")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_bj = dt_utc + timedelta(hours=8)
        return dt_bj

    def _format_weekday(self, dt):
        days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        return days[dt.weekday()]

    def _get_session_status(self, date_str, time_str):
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%SZ")
        dt_utc = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now > dt_utc + timedelta(hours=2):
            return "completed"
        elif now > dt_utc - timedelta(minutes=30):
            return "live"
        else:
            return "upcoming"

    def _find_race_by_round(self, races, round_num):
        for race in races:
            if int(race["round"]) == round_num:
                return race
        return None

    def _find_next_race(self, races):
        now = datetime.now(timezone.utc)
        for race in races:
            race_date = datetime.strptime(race["date"], "%Y-%m-%d")
            race_time = datetime.strptime(race.get("time", "00:00:00Z"), "%H:%M:%SZ")
            race_dt = race_date.replace(hour=race_time.hour, minute=race_time.minute, tzinfo=timezone.utc)
            if now < race_dt + timedelta(hours=2):
                return race
        return races[-1] if races else None

    def draw_race_detail(self, json_path="f1_race_schedule.json", round_num=None):
        print(">>> [引擎启动] 正在生成单场大奖赛赛程...")
        if not os.path.exists(json_path):
            print(f"❌ 文件不存在: {json_path}")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        races = data["MRData"]["RaceTable"]["Races"]
        season = data["MRData"]["RaceTable"]["season"]

        if round_num is not None:
            race = self._find_race_by_round(races, round_num)
            if not race:
                print(f"❌ 未找到第 {round_num} 轮比赛")
                return
        else:
            race = self._find_next_race(races)
            if not race:
                print("❌ 未找到任何比赛")
                return

        sessions = self._build_session_list(race)
        is_sprint = "Sprint" in race

        # ── 布局 ──
        canvas_w = 850
        header_h = 240
        day_header_h = 36
        session_h = 68
        footer_h = 60

        # 计算日期分组
        day_groups = []
        current_day = None
        for s in sessions:
            day_key = s["bj_time"].strftime("%Y-%m-%d")
            if day_key != current_day:
                current_day = day_key
                day_groups.append(day_key)

        total_rows = len(sessions) + len(day_groups)
        canvas_h = header_h + (len(day_groups) * day_header_h) + (len(sessions) * session_h) + footer_h + 20

        canvas = Image.new('RGBA', (canvas_w, canvas_h), color=self.bg_color)
        draw = ImageDraw.Draw(canvas)

        # ── 1. Header ──
        draw.rectangle([0, 0, canvas_w, header_h - 10], fill=(15, 15, 20, 255))

        red_line_x = 210
        draw.text((red_line_x, 35), f"ROUND {race['round']}", font=self.font_medium, fill=self.f1_red)

        gp_name = race["raceName"].upper()
        draw.text((50, 75), gp_name, font=self.font_bold, fill=self.text_color)

        circuit = race["Circuit"]["circuitName"]
        locality = race["Circuit"]["Location"]["locality"]
        country = race["Circuit"]["Location"]["country"]
        draw.text((50, 135), circuit, font=self.font_regular, fill=self.dim_color)
        draw.text((50, 170), f"{locality}, {country}", font=self.font_small, fill=self.dim_color)

        # 冲刺赛标记
        if is_sprint:
            tag_font = ImageFont.truetype("assets/fonts/Formula1-Regular.ttf", 14)
            tag_text = "SPRINT WEEKEND"
            # 动态计算文本宽度，确保紫色背景完全覆盖
            tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
            text_w = tag_bbox[2] - tag_bbox[0]
            tag_padding = 16  # 左右各8px内边距
            tag_w = text_w + tag_padding
            tag_h = 24
            tag_x = canvas_w - 50 - tag_w
            tag_y = 36
            draw.rounded_rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + tag_h], radius=4, fill=self.sprint_color)
            draw.text((tag_x + tag_w // 2, tag_y + tag_h // 2), tag_text, font=tag_font, fill=self.text_color, anchor="mm")

        # 日期范围
        race_date = datetime.strptime(race["date"], "%Y-%m-%d")
        earliest = race_date
        for key in ["FirstPractice", "SprintQualifying", "Sprint", "SecondPractice", "ThirdPractice", "Qualifying"]:
            if key in race:
                d = datetime.strptime(race[key]["date"], "%Y-%m-%d")
                if d < earliest:
                    earliest = d
        date_range = f"{earliest.strftime('%b %d')} - {race_date.strftime('%b %d, %Y')}"
        draw.text((50, 205), date_range, font=self.font_medium, fill=self.yellow_color)

        # ── 2. Session 列表 ──
        y_cursor = header_h
        last_date = None
        session_idx = 0

        for session in sessions:
            bj_dt = session["bj_time"]
            session_date = bj_dt.strftime("%Y-%m-%d")
            weekday = self._format_weekday(bj_dt)
            time_str = bj_dt.strftime("%H:%M")
            date_display = bj_dt.strftime("%m/%d")

            # 日期分组标题
            if session_date != last_date:
                last_date = session_date
                day_label = f"{weekday}  {bj_dt.strftime('%B %d').upper()}"
                draw.rectangle([50, y_cursor, canvas_w - 50, y_cursor + day_header_h], fill=(35, 35, 48, 255))
                draw.text((70, y_cursor + day_header_h // 2), day_label, font=self.font_small, fill=self.dim_color, anchor="lm")
                y_cursor += day_header_h

            # 行背景
            if session_idx % 2 == 0:
                draw.rectangle([50, y_cursor + 2, canvas_w - 50, y_cursor + session_h - 2], fill=self.stripe_color)

            center_y = y_cursor + (session_h // 2)

            # Session 状态
            status = session["status"]
            if status == "completed":
                dot_color = self.dim_color
                name_color = self.dim_color
                time_color = self.dim_color
            elif status == "live":
                dot_color = self.green_color
                name_color = self.green_color
                time_color = self.green_color
            else:
                dot_color = self.text_color
                name_color = self.text_color
                time_color = self.yellow_color

            # 状态圆点
            dot_r = 5
            draw.ellipse([75 - dot_r, center_y - dot_r, 75 + dot_r, center_y + dot_r], fill=dot_color)

            # Session 名称
            draw.text((100, center_y), session["name"], font=self.font_medium, fill=name_color, anchor="lm")

            # 时间（右侧，等宽渲染确保对齐，冒号适度收窄）
            self._draw_fixed_width_text(draw, time_str, canvas_w - 70, center_y, self.font_large, time_color, char_width=26, align="right", narrow_chars={":"}, narrow_width=14)

            # LIVE 标签
            if status == "live":
                live_font = ImageFont.truetype("assets/fonts/Formula1-Bold.ttf", 13)
                live_x = canvas_w - 68
                draw.rounded_rectangle([live_x, center_y - 10, live_x + 38, center_y + 6], radius=3, fill=self.f1_red)
                draw.text((live_x + 19, center_y - 2), "LIVE", font=live_font, fill=self.text_color, anchor="mm")

            y_cursor += session_h
            session_idx += 1

        # ── 3. Footer ──
        footer_y = canvas_h - footer_h
        draw.rectangle([0, footer_y, canvas_w, canvas_h], fill=self.f1_red)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        draw.text((20, footer_y + 18), f"@F1y/Car | TIMES IN UTC+8 | RENDERED: {current_time}", font=self.font_small, fill=self.text_color)

        # ── 4. 叠加 F1 Logo ──
        apply_f1_logo(canvas, max_width_ratio=0.10, margin=(24, 32), opacity=232, position="top-left")

        output_name = f"race_detail_r{race['round']}.png"
        canvas.save(output_name)
        print(f"🏁 R{race['round']} {race['raceName']} 赛程渲染完成！→ {output_name}")

    def _build_session_list(self, race):
        sessions = []

        session_map = {
            "FirstPractice": "PRACTICE 1",
            "SecondPractice": "PRACTICE 2",
            "ThirdPractice": "PRACTICE 3",
            "SprintQualifying": "SPRINT QUALIFYING",
            "Sprint": "SPRINT RACE",
            "Qualifying": "QUALIFYING",
        }

        for key, name in session_map.items():
            if key in race:
                s = race[key]
                bj_time = self._utc_to_beijing(s["date"], s["time"])
                status = self._get_session_status(s["date"], s["time"])
                sessions.append({
                    "name": name,
                    "bj_time": bj_time,
                    "status": status,
                })

        # 正赛
        bj_time = self._utc_to_beijing(race["date"], race.get("time", "00:00:00Z"))
        status = self._get_session_status(race["date"], race.get("time", "00:00:00Z"))
        sessions.append({
            "name": "RACE",
            "bj_time": bj_time,
            "status": status,
        })

        sessions.sort(key=lambda s: s["bj_time"])
        return sessions


if __name__ == "__main__":
    F1RaceDetailRenderer().draw_race_detail()
