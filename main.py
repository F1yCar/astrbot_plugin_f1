import asyncio
import importlib.util
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


def _ascii_case_variants(text: str) -> set[str]:
    """生成 ASCII 字母大小写全变体，用于命令大小写不敏感匹配。"""
    variants = {""}
    for ch in text:
        if ch.isascii() and ch.isalpha():
            variants = {prefix + ch.lower() for prefix in variants} | {prefix + ch.upper() for prefix in variants}
        else:
            variants = {prefix + ch for prefix in variants}
    variants.discard(text)
    return variants


@register("astrbot_plugin_f1", "F1yCar", "F1 数据更新与信息图渲染插件", "1.0.0")
class F1Plugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.plugin_root = Path(__file__).resolve().parent
        self.project_root = self._detect_project_root()
        self.runtime_data_root = self._detect_runtime_data_root()
        self.output_dir = self.runtime_data_root / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets = self._load_assets()
        self.driver_team_map, self.driver_code_map, self.driver_number_map = self._load_driver_meta()
        self.driver_aliases, self.team_aliases = self._build_aliases()

    async def initialize(self):
        logger.info(f"[F1Plugin] plugin_root = {self.plugin_root}")
        logger.info(f"[F1Plugin] project_root = {self.project_root}")
        logger.info(f"[F1Plugin] runtime_data_root = {self.runtime_data_root}")

    def _is_valid_project_root(self, p: Path) -> bool:
        required = [
            "f1_driver_rank_renderer.py",
            "f1_team_rank_renderer.py",
            "f1_driver_renderer.py",
            "f1_team_renderer.py",
            "f1_data_exporter.py",
            "f1_local_assets.json",
            "assets",
        ]
        return all((p / item).exists() for item in required)

    def _detect_project_root(self) -> Path:
        """
        QQ 版默认使用插件目录（自包含）。
        仅当设置 F1_USE_EXTERNAL_PROJECT=1 时，才尝试读取外部项目目录。
        """
        env_root = os.environ.get("F1_PROJECT_ROOT")
        current = self.plugin_root
        use_external = os.environ.get("F1_USE_EXTERNAL_PROJECT", "0").strip().lower() in {"1", "true", "yes", "on"}

        if self._is_valid_project_root(current) and not use_external:
            return current

        candidates: list[Path] = []
        if env_root and Path(env_root).exists():
            candidates.append(Path(env_root))
        candidates.extend(list(current.parents))
        candidates.append(current)

        for p in candidates:
            if self._is_valid_project_root(p):
                return p

        return current

    def _detect_runtime_data_root(self) -> Path:
        """
        持久化输出目录：优先放到 AstrBot 的 data 目录，避免插件更新时被覆盖。
        可通过 F1_RUNTIME_DATA_DIR 覆盖。
        """
        env_dir = os.environ.get("F1_RUNTIME_DATA_DIR")
        if env_dir:
            return Path(env_dir)

        for p in self.plugin_root.parents:
            if p.name.lower() == "data":
                return p / "plugins_data" / "astrbot_plugin_f1"

        return self.plugin_root / "data"

    def _load_assets(self) -> dict:
        assets_path = self.project_root / "f1_local_assets.json"
        if not assets_path.exists():
            return {"drivers": {}, "teams": {}}
        with open(assets_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _normalize(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"[\s_\-\.]+", "", text.strip().lower())

    @staticmethod
    def _match_local_driver_id(api_id: str, local_ids: list[str]) -> str | None:
        api_norm = api_id.lower()
        for local_id in local_ids:
            if local_id in api_norm or api_norm in local_id:
                return local_id
        return None

    @staticmethod
    def _match_local_team_id(api_id: str) -> str:
        mapping = {
            "red_bull": "redbullracing",
            "rb": "racingbulls",
            "aston_martin": "astonmartin",
            "haasf1team": "haas",
        }
        return mapping.get(api_id.lower(), api_id.lower())

    def _load_driver_meta(self) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        standings_path = self.project_root / "f1_driver_standings.json"
        driver_team_map: dict[str, str] = {}
        driver_code_map: dict[str, str] = {}
        driver_number_map: dict[str, str] = {}

        if not standings_path.exists():
            return driver_team_map, driver_code_map, driver_number_map

        try:
            with open(standings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            standings = data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
            local_driver_ids = list(self.assets.get("drivers", {}).keys())
            for item in standings:
                api_driver_id = item["Driver"]["driverId"]
                local_driver_id = self._match_local_driver_id(api_driver_id, local_driver_ids)
                if not local_driver_id:
                    continue
                constructor_api = item.get("Constructors", [{}])[0].get("constructorId", "")
                driver_team_map[local_driver_id] = self._match_local_team_id(constructor_api)
                if item["Driver"].get("code"):
                    driver_code_map[local_driver_id] = item["Driver"]["code"].upper()
                if item["Driver"].get("permanentNumber"):
                    driver_number_map[local_driver_id] = str(item["Driver"]["permanentNumber"])
        except Exception as e:
            logger.warning(f"[F1Plugin] load standings meta failed: {e}")

        return driver_team_map, driver_code_map, driver_number_map

    def _build_aliases(self) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        driver_aliases: dict[str, set[str]] = {}
        team_aliases: dict[str, set[str]] = {}

        def add(mapping: dict[str, set[str]], alias: str, target: str):
            key = self._normalize(alias)
            if not key:
                return
            mapping.setdefault(key, set()).add(target)

        drivers = self.assets.get("drivers", {})
        for driver_id, info in drivers.items():
            add(driver_aliases, driver_id, driver_id)
            name = info.get("name", "")
            add(driver_aliases, name, driver_id)
            parts = name.split()
            if parts:
                add(driver_aliases, parts[-1], driver_id)

        for driver_id, code in self.driver_code_map.items():
            add(driver_aliases, code, driver_id)
        for driver_id, num in self.driver_number_map.items():
            add(driver_aliases, num, driver_id)

        driver_zh = {
            "维斯塔潘": "verstappen",
            "汉密尔顿": "hamilton",
            "勒克莱尔": "leclerc",
            "拉塞尔": "russell",
            "诺里斯": "norris",
            "皮亚斯特里": "piastri",
            "阿隆索": "alonso",
            "赛恩斯": "sainz",
            "加斯利": "gasly",
            "奥康": "ocon",
            "阿尔本": "albon",
            "斯托尔": "stroll",
            "博塔斯": "bottas",
            "安东内利": "antonelli",
            "贝尔曼": "bearman",
            "博托莱托": "bortoleto",
            "科拉平托": "colapinto",
            "哈贾尔": "hadjar",
            "霍肯伯格": "hulkenberg",
            "劳森": "lawson",
            "林德布拉德": "lindblad",
            "佩雷兹": "perez",
        }
        for k, v in driver_zh.items():
            if v in drivers:
                add(driver_aliases, k, v)

        teams = self.assets.get("teams", {})
        for team_id, info in teams.items():
            add(team_aliases, team_id, team_id)
            add(team_aliases, info.get("name", ""), team_id)

        team_zh = {
            "红牛": "redbullracing",
            "法拉利": "ferrari",
            "梅赛德斯": "mercedes",
            "迈凯伦": "mclaren",
            "阿斯顿马丁": "astonmartin",
            "哈斯": "haas",
            "威廉姆斯": "williams",
            "阿尔派": "alpine",
            "小红牛": "racingbulls",
            "奥迪": "audi",
            "凯迪拉克": "cadillac",
        }
        for k, v in team_zh.items():
            if v in teams:
                add(team_aliases, k, v)

        return driver_aliases, team_aliases

    def _resolve_alias(self, query: str, alias_map: dict[str, set[str]]) -> str | None:
        key = self._normalize(query)
        if not key:
            return None

        exact = alias_map.get(key)
        if exact:
            if len(exact) == 1:
                return next(iter(exact))
            return None

        candidates = list(alias_map.keys())
        fuzzy = get_close_matches(key, candidates, n=1, cutoff=0.72)
        if fuzzy:
            target_ids = alias_map.get(fuzzy[0], set())
            if len(target_ids) == 1:
                return next(iter(target_ids))
        return None

    def _suggest_alias_targets(self, query: str, alias_map: dict[str, set[str]], limit: int = 3) -> list[str]:
        key = self._normalize(query)
        if not key:
            return []
        candidates = list(alias_map.keys())
        fuzzy = get_close_matches(key, candidates, n=limit, cutoff=0.55)
        suggestions: list[str] = []
        for candidate in fuzzy:
            for target in sorted(alias_map.get(candidate, set())):
                if target not in suggestions:
                    suggestions.append(target)
                if len(suggestions) >= limit:
                    return suggestions
        return suggestions

    def _race_round_bounds(self) -> tuple[int, int] | None:
        schedule_path = self.project_root / "f1_race_schedule.json"
        if not schedule_path.exists():
            return None
        try:
            with open(schedule_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            rounds = [int(r.get("round")) for r in races if str(r.get("round", "")).isdigit()]
            if not rounds:
                return None
            return min(rounds), max(rounds)
        except Exception:
            return None

    @property
    def _auto_update_state_path(self) -> Path:
        return self.runtime_data_root / "auto_update_state.json"

    def _load_auto_update_state(self) -> dict:
        path = self._auto_update_state_path
        if not path.exists():
            return {"processed_sessions": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"processed_sessions": []}
            sessions = data.get("processed_sessions", [])
            if not isinstance(sessions, list):
                sessions = []
            return {"processed_sessions": [str(s) for s in sessions]}
        except Exception:
            return {"processed_sessions": []}

    def _save_auto_update_state(self, state: dict):
        path = self._auto_update_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_utc_datetime(date_str: str, time_str: str | None) -> datetime | None:
        if not date_str:
            return None
        t = (time_str or "00:00:00Z").strip()
        try:
            dt = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M:%SZ")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _collect_finished_score_sessions(self) -> list[tuple[str, datetime, str]]:
        """收集已结束（+2h）的积分相关节点：Sprint 与 Race。"""
        schedule_path = self.project_root / "f1_race_schedule.json"
        if not schedule_path.exists():
            return []

        try:
            with open(schedule_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            race_table = data.get("MRData", {}).get("RaceTable", {})
            season = str(race_table.get("season", "current"))
            races = race_table.get("Races", [])
            now = datetime.now(timezone.utc)
            finished: list[tuple[str, datetime, str]] = []

            for race in races:
                round_str = str(race.get("round", "?"))

                # 冲刺赛节点
                sprint = race.get("Sprint")
                if isinstance(sprint, dict):
                    s_dt = self._parse_utc_datetime(sprint.get("date", ""), sprint.get("time"))
                    if s_dt and now >= s_dt + timedelta(hours=2):
                        token = f"{season}-r{round_str}-sprint"
                        finished.append((token, s_dt, f"R{round_str} Sprint"))

                # 正赛节点
                r_dt = self._parse_utc_datetime(str(race.get("date", "")), race.get("time"))
                if r_dt and now >= r_dt + timedelta(hours=2):
                    token = f"{season}-r{round_str}-race"
                    finished.append((token, r_dt, f"R{round_str} Race"))

            finished.sort(key=lambda x: x[1])
            return finished
        except Exception as e:
            logger.warning(f"[F1Plugin] parse schedule for auto update failed: {e}")
            return []

    def _run_export_standings_only(self):
        with self._cwd():
            mod = self._load_module_from_file("f1_data_exporter.py", "f1_data_exporter")

            async def _run():
                exporter = mod.F1DataExporter()
                await exporter.export_standings()

            asyncio.run(_run())

        # 更新后刷新索引与别名
        self.assets = self._load_assets()
        self.driver_team_map, self.driver_code_map, self.driver_number_map = self._load_driver_meta()
        self.driver_aliases, self.team_aliases = self._build_aliases()

    def _auto_update_standings_if_needed(self) -> str | None:
        """
        当检测到“冲刺赛/正赛已结束且尚未处理”时，自动更新一次积分榜。
        返回提示文案；无更新时返回 None。
        """
        finished = self._collect_finished_score_sessions()
        if not finished:
            return None

        state = self._load_auto_update_state()
        processed = set(state.get("processed_sessions", []))

        pending = [(t, dt, title) for t, dt, title in finished if t not in processed]
        if not pending:
            return None

        self._run_export_standings_only()

        for token, _, _ in pending:
            processed.add(token)
        state["processed_sessions"] = sorted(processed)
        self._save_auto_update_state(state)

        latest_title = pending[-1][2]
        return f"🔄 检测到赛后节点（最新: {latest_title}），已自动更新车手/车队积分。"

    async def _maybe_auto_update_standings(self) -> str | None:
        try:
            return await asyncio.to_thread(self._auto_update_standings_if_needed)
        except Exception as e:
            logger.warning(f"[F1Plugin] auto update standings failed: {e}")
            return None

    def _load_module_from_file(self, filename: str, module_name: str):
        file_path = self.project_root / filename
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载模块: {file_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @contextmanager
    def _cwd(self):
        old = Path.cwd()
        os.chdir(self.project_root)
        try:
            yield
        finally:
            os.chdir(old)

    def _render_driver_rank(self) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_driver_rank_renderer.py", "f1_driver_rank_renderer")
            mod.F1DriverRankRenderer().draw_rank_card()
            generated = self.project_root / "driver_rankings.png"
            target = self.output_dir / "driver_rankings.png"
            if generated.exists():
                generated.replace(target)
                return target
            raise FileNotFoundError("未生成车手积分榜图片: driver_rankings.png")

    def _render_driver_card(self, driver_id: str) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_driver_renderer.py", "f1_driver_renderer")
            team_id = self.driver_team_map.get(driver_id, "mercedes")
            mod.F1Renderer().draw_test_driver_card(driver_id=driver_id, team_id=team_id)
            generated = self.project_root / "test_driver_card_4x3.png"
            target = self.output_dir / f"driver_card_{driver_id}.png"
            if generated.exists():
                generated.replace(target)
                return target
            raise FileNotFoundError("未生成车手卡图片: test_driver_card_4x3.png")

    def _render_team_rank(self) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_team_rank_renderer.py", "f1_team_rank_renderer")
            mod.F1TeamRankRenderer().draw_team_rank()
            generated = self.project_root / "team_rankings.png"
            target = self.output_dir / "team_rankings.png"
            if generated.exists():
                generated.replace(target)
                return target
            raise FileNotFoundError("未生成车队积分榜图片: team_rankings.png")

    def _render_team_card(self, team_id: str) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_team_renderer.py", "f1_team_renderer")
            mod.F1TeamRenderer().draw_team_card(team_id=team_id)
            generated = self.project_root / f"team_banner_{team_id}.png"
            target = self.output_dir / f"team_banner_{team_id}.png"
            if generated.exists():
                generated.replace(target)
                return target
            raise FileNotFoundError(f"未生成车队卡图片: team_banner_{team_id}.png")

    def _render_calendar(self) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_calendar_renderer.py", "f1_calendar_renderer")
            mod.F1CalendarRenderer().draw_calendar()
            generated = self.project_root / "race_calendar.png"
            target = self.output_dir / "race_calendar.png"
            if generated.exists():
                generated.replace(target)
                return target
            raise FileNotFoundError("未生成赛历图片: race_calendar.png")

    def _render_race_detail(self, round_num: int | None) -> Path:
        with self._cwd():
            mod = self._load_module_from_file("f1_race_detail_renderer.py", "f1_race_detail_renderer")
            mod.F1RaceDetailRenderer().draw_race_detail(round_num=round_num)
            if round_num is not None:
                generated = self.project_root / f"race_detail_r{round_num}.png"
                target = self.output_dir / f"race_detail_r{round_num}.png"
                if generated.exists():
                    generated.replace(target)
                    return target
                raise FileNotFoundError(f"未找到第 {round_num} 轮赛程图片")

            # 自动轮次时，尝试找最新生成文件
            matches = sorted(self.project_root.glob("race_detail_r*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not matches:
                raise FileNotFoundError("未找到 race_detail_r*.png")
            target = self.output_dir / matches[0].name
            matches[0].replace(target)
            return target

    def _run_export_data(self):
        with self._cwd():
            mod = self._load_module_from_file("f1_data_exporter.py", "f1_data_exporter")
            asyncio.run(mod.run_pipeline())
        # 数据更新后刷新索引与别名
        self.assets = self._load_assets()
        self.driver_team_map, self.driver_code_map, self.driver_number_map = self._load_driver_meta()
        self.driver_aliases, self.team_aliases = self._build_aliases()

    @staticmethod
    def _extract_arg(raw_message: str) -> str:
        raw = raw_message.strip()
        if raw.startswith("/"):
            raw = raw[1:]
        parts = raw.split(maxsplit=1)
        if len(parts) < 2:
            return ""
        return parts[1].strip()

    def _driver_display_name(self, driver_id: str) -> str:
        return self.assets.get("drivers", {}).get(driver_id, {}).get("name", driver_id)

    def _team_display_name(self, team_id: str) -> str:
        return self.assets.get("teams", {}).get(team_id, {}).get("name", team_id)

    @filter.command("f1help", alias=_ascii_case_variants("f1help"))
    @filter.command("f1帮助")
    async def f1help(self, event: AstrMessageEvent):
        """显示 F1 插件命令帮助"""
        help_image_candidates = [
            self.project_root / "help.png",
            self.project_root / "Help.png",
            self.plugin_root / "help.png",
            self.plugin_root / "Help.png",
        ]
        for img_path in help_image_candidates:
            if img_path.exists():
                yield event.image_result(str(img_path))
                break

        yield event.plain_result(
            "F1 插件命令:\n"
            "/f1update - 拉取最新数据\n"
            "/f1driver [车手关键字] - 车手榜 / 指定车手图（支持全称/缩写/车号）\n"
            "/f1team [车队关键字] - 车队榜 / 指定车队图（支持模糊）\n"
            "/f1calendar - 生成赛历\n"
            "/f1race [轮次] - 生成单场赛程（不填轮次则自动下一场）\n"
            "/f1all - 一次性生成并发送常用三图\n"
            "/f1status - 检查插件环境状态\n"
            "中文别名: /车手 /车队 /赛历 /赛程 /更新 /状态"
        )

    @filter.command("f1update", alias=_ascii_case_variants("f1update"))
    @filter.command("更新")
    @filter.command("f1更新", alias=_ascii_case_variants("f1更新"))
    async def f1update(self, event: AstrMessageEvent):
        """拉取最新 F1 数据"""
        yield event.plain_result("开始拉取 F1 数据，请稍候...")
        try:
            await asyncio.to_thread(self._run_export_data)
            yield event.plain_result("✅ 数据更新完成")
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 数据更新失败: {e}")

    @filter.command("f1driver", alias=_ascii_case_variants("f1driver"))
    @filter.command("车手")
    @filter.command("f1车手", alias=_ascii_case_variants("f1车手"))
    async def f1driver(self, event: AstrMessageEvent):
        """生成车手积分榜或指定车手图"""
        auto_msg = await self._maybe_auto_update_standings()
        if auto_msg:
            yield event.plain_result(auto_msg)

        query = self._extract_arg(event.message_str)
        if not query:
            yield event.plain_result("正在生成车手积分榜...")
            try:
                path = await asyncio.to_thread(self._render_driver_rank)
                yield event.image_result(str(path))
            except Exception as e:
                logger.exception(e)
                yield event.plain_result(f"❌ 渲染失败: {e}")
            return

        driver_id = self._resolve_alias(query, self.driver_aliases)
        if not driver_id:
            suggestions = self._suggest_alias_targets(query, self.driver_aliases)
            suggestion_text = ""
            if suggestions:
                names = [self._driver_display_name(s) for s in suggestions]
                suggestion_text = f"\n你可能想找: {', '.join(names)}"
            yield event.plain_result(
                f"❌ 未匹配到车手: {query}\n"
                "可尝试: 全名(如 Max Verstappen) / 缩写(VER) / 车号(1)"
                f"{suggestion_text}"
            )
            return

        display_name = self._driver_display_name(driver_id)
        yield event.plain_result(f"正在生成车手图: {display_name}...")
        try:
            path = await asyncio.to_thread(self._render_driver_card, driver_id)
            yield event.image_result(str(path))
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 渲染失败: {e}")

    @filter.command("f1team", alias=_ascii_case_variants("f1team"))
    @filter.command("车队")
    @filter.command("f1车队", alias=_ascii_case_variants("f1车队"))
    async def f1team(self, event: AstrMessageEvent):
        """生成车队积分榜或指定车队图"""
        auto_msg = await self._maybe_auto_update_standings()
        if auto_msg:
            yield event.plain_result(auto_msg)

        query = self._extract_arg(event.message_str)
        if not query:
            yield event.plain_result("正在生成车队积分榜...")
            try:
                path = await asyncio.to_thread(self._render_team_rank)
                yield event.image_result(str(path))
            except Exception as e:
                logger.exception(e)
                yield event.plain_result(f"❌ 渲染失败: {e}")
            return

        team_id = self._resolve_alias(query, self.team_aliases)
        if not team_id:
            suggestions = self._suggest_alias_targets(query, self.team_aliases)
            suggestion_text = ""
            if suggestions:
                names = [self._team_display_name(s) for s in suggestions]
                suggestion_text = f"\n你可能想找: {', '.join(names)}"
            yield event.plain_result(
                f"❌ 未匹配到车队: {query}\n"
                "可尝试: team id(mercedes) / 英文名(Mercedes) / 中文名(梅赛德斯)"
                f"{suggestion_text}"
            )
            return

        display_name = self._team_display_name(team_id)
        yield event.plain_result(f"正在生成车队图: {display_name}...")
        try:
            path = await asyncio.to_thread(self._render_team_card, team_id)
            yield event.image_result(str(path))
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 渲染失败: {e}")

    @filter.command("f1calendar", alias=_ascii_case_variants("f1calendar"))
    @filter.command("赛历")
    @filter.command("f1赛历", alias=_ascii_case_variants("f1赛历"))
    async def f1calendar(self, event: AstrMessageEvent):
        """生成并发送赛季赛历"""
        yield event.plain_result("正在生成赛季赛历...")
        try:
            path = await asyncio.to_thread(self._render_calendar)
            yield event.image_result(str(path))
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 渲染失败: {e}")

    @filter.command("f1race", alias=_ascii_case_variants("f1race"))
    @filter.command("赛程")
    @filter.command("f1赛程", alias=_ascii_case_variants("f1赛程"))
    async def f1race(self, event: AstrMessageEvent):
        """生成并发送单场赛程，格式：/f1race 或 /f1race 5"""
        raw = event.message_str.strip()
        parts = raw.split()
        round_num = None
        if len(parts) >= 2:
            try:
                round_num = int(parts[1])
            except ValueError:
                yield event.plain_result("❌ 轮次必须是数字，例如 /f1race 5")
                return

        if round_num is not None and round_num <= 0:
            yield event.plain_result("❌ 轮次必须是正整数，例如 /f1race 5")
            return

        if round_num is not None:
            bounds = self._race_round_bounds()
            if bounds is not None:
                min_round, max_round = bounds
                if round_num < min_round or round_num > max_round:
                    yield event.plain_result(
                        f"❌ 第 {round_num} 轮不存在，当前赛季可用轮次范围: {min_round}-{max_round}"
                    )
                    return

        tip = f"正在生成 R{round_num} 赛程..." if round_num else "正在生成下一场赛程..."
        yield event.plain_result(tip)
        try:
            path = await asyncio.to_thread(self._render_race_detail, round_num)
            yield event.image_result(str(path))
        except FileNotFoundError as e:
            yield event.plain_result(f"❌ {e}")
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 渲染失败: {e}")

    @filter.command("f1all", alias=_ascii_case_variants("f1all"))
    @filter.command("全部")
    @filter.command("f1全部", alias=_ascii_case_variants("f1全部"))
    async def f1all(self, event: AstrMessageEvent):
        """一次性发送常用三图：车手榜、车队榜、赛历"""
        auto_msg = await self._maybe_auto_update_standings()
        if auto_msg:
            yield event.plain_result(auto_msg)

        yield event.plain_result("正在生成常用三图（车手榜/车队榜/赛历）...")
        try:
            driver_rank_path = await asyncio.to_thread(self._render_driver_rank)
            team_rank_path = await asyncio.to_thread(self._render_team_rank)
            calendar_path = await asyncio.to_thread(self._render_calendar)
            yield event.image_result(str(driver_rank_path))
            yield event.image_result(str(team_rank_path))
            yield event.image_result(str(calendar_path))
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"❌ 批量渲染失败: {e}")

    @filter.command("f1status", alias=_ascii_case_variants("f1status"))
    @filter.command("状态")
    @filter.command("f1状态", alias=_ascii_case_variants("f1状态"))
    async def f1status(self, event: AstrMessageEvent):
        """检查插件运行状态与关键文件存在性"""
        checks = {
            "f1_data_exporter.py": (self.project_root / "f1_data_exporter.py").exists(),
            "f1_driver_renderer.py": (self.project_root / "f1_driver_renderer.py").exists(),
            "f1_team_renderer.py": (self.project_root / "f1_team_renderer.py").exists(),
            "f1_driver_rank_renderer.py": (self.project_root / "f1_driver_rank_renderer.py").exists(),
            "f1_team_rank_renderer.py": (self.project_root / "f1_team_rank_renderer.py").exists(),
            "f1_calendar_renderer.py": (self.project_root / "f1_calendar_renderer.py").exists(),
            "f1_race_detail_renderer.py": (self.project_root / "f1_race_detail_renderer.py").exists(),
            "f1_local_assets.json": (self.project_root / "f1_local_assets.json").exists(),
            "assets/f1_logo.png": (self.project_root / "assets" / "f1_logo.png").exists(),
            "outputs/": self.output_dir.exists(),
        }
        ok = sum(1 for v in checks.values() if v)
        mode = "external" if self.project_root != self.plugin_root else "plugin-local"
        lines = [
            f"插件目录: {self.plugin_root}",
            f"数据目录: {self.project_root}",
            f"运行数据目录: {self.runtime_data_root}",
            f"模式: {mode}",
            f"状态: {ok}/{len(checks)}",
        ]
        lines.extend([f"{'✅' if exists else '❌'} {name}" for name, exists in checks.items()])
        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        logger.info("[F1Plugin] terminated")
