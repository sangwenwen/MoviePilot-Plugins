from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType


class StrmSubscribeGuard(_PluginBase):
    """STRM 订阅隔离

    整理 strm 到 strmlink 库时，不把集数写进订阅账本，避免订阅被误判完成。
    做法是接管 MoviePilot 内置的整理入库事件处理，不改任何镜像文件。
    """

    plugin_name = "STRM 订阅隔离"
    plugin_desc = "整理 strm 时不写入订阅账本，订阅完成度只按真实文件（link 库）判定。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot/main/app/static/img/logo.png"
    plugin_version = "1.0.0"
    plugin_author = "Wen/Hermes"
    author_url = "https://github.com/jxxghp/MoviePilot"
    plugin_config_prefix = "strmsubscribeguard_"
    plugin_order = 30
    auth_level = 1

    _enabled = False
    _patched = False
    _hits = 0

    def init_plugin(self, config: dict = None):
        if config and "enabled" in config:
            self._enabled = bool(config.get("enabled"))
        else:
            self._enabled = True
        if self._enabled:
            self._install_guard()

    def get_state(self) -> bool:
        return True

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "本插件加载即生效：整理到 strmlink 库的 strm 不会写入订阅账本，"
                                                    "订阅的已入库/缺失集数只按真实文件库判定。",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ], {}

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "success" if self._patched else "error",
                                    "variant": "tonal",
                                    "text": f"内置整理入库处理：{'已接管' if self._patched else '未接管'}；"
                                            f"本次启动累计拦截 {self._hits} 次 strm 整理。",
                                },
                            }
                        ],
                    }
                ],
            }
        ]

    def stop_service(self):
        self._restore()

    # ------------------------------------------------------------------

    def _install_guard(self):
        try:
            from app.chain.subscribe.library import SubscribeLibraryOwner

            current = SubscribeLibraryOwner._sync_library_progress_after_transfer
            if getattr(current, "_strm_guarded", False):
                self._patched = True
                logger.info("STRM 订阅隔离：内置处理已被接管，跳过重复安装")
                return

            original = current
            plugin = self

            def guarded(owner_self, event):
                try:
                    event_data = event.event_data if isinstance(event.event_data, dict) else {}
                    transfer_repr = str(event_data.get("transferinfo") or "").lower()
                    if "strmlink" in transfer_repr or ".strm" in transfer_repr:
                        plugin._hits += 1
                        mediainfo = event_data.get("mediainfo")
                        title = getattr(mediainfo, "title_year", "") if mediainfo is not None else ""
                        logger.info(f"STRM 订阅隔离：跳过订阅账本写入 -> {title}")
                        return None
                except Exception as err:
                    logger.warning(f"STRM 订阅隔离：判断整理目标失败，放行，{err}")
                return original(owner_self, event)

            guarded._strm_guarded = True
            guarded._strm_original = original
            SubscribeLibraryOwner._sync_library_progress_after_transfer = guarded
            self._patched = True
            logger.info("STRM 订阅隔离：已接管内置整理入库事件处理")
        except Exception as err:
            self._patched = False
            logger.error(f"STRM 订阅隔离：接管失败，{err}")

    def _restore(self):
        try:
            from app.chain.subscribe.library import SubscribeLibraryOwner

            current = SubscribeLibraryOwner._sync_library_progress_after_transfer
            original = getattr(current, "_strm_original", None)
            if original is not None:
                SubscribeLibraryOwner._sync_library_progress_after_transfer = original
                logger.info("STRM 订阅隔离：已恢复内置整理入库处理")
        except Exception as err:
            logger.warning(f"STRM 订阅隔离：恢复失败，{err}")
        self._patched = False