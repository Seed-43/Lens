# window.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from gettext import gettext as _
from io import BytesIO
from mimetypes import guess_type
from urllib.parse import urlparse

from gi.repository import Adw, Gdk, GLib, Gio, Gtk
from loguru import logger

from lens.config import RESOURCE_PREFIX
from lens.gobject_worker import GObjectWorker
from lens.language_manager import language_manager
from lens.services.clipboard_service import ClipboardService, clipboard_service
from lens.services.history_service import HistoryEntry, history_service
from lens.services.ocr_engine_service import ocr_engine_service, ENGINES, ENGINE_KEYS, BUILTIN_ENGINES
from lens.services.hotkey_service import hotkey_service
from lens.services.screenshot_service import ScreenshotService
from lens.widgets.language_popover import LanguagePopover
from lens.widgets.manage_languages_popover import ManageLanguagesPopover


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/window.ui")
class LensWindow(Adw.ApplicationWindow):
    """
    Main application window for Lens.

    Owns the sidebar (Lens + Settings tabs), the content area (text view /
    empty state), and the overlay history panel.
    """

    __gtype_name__ = "LensWindow"

    # ------------------------------------------------------------------ #
    # Template children                                                    #
    # ------------------------------------------------------------------ #

    toast_overlay:            Adw.ToastOverlay    = Gtk.Template.Child()
    main_nav:                 Adw.NavigationView  = Gtk.Template.Child()
    app_icon:                 Gtk.Image           = Gtk.Template.Child()
    version_label:            Gtk.Label           = Gtk.Template.Child()
    tab_lens:                 Gtk.ToggleButton    = Gtk.Template.Child()
    tab_settings:             Gtk.ToggleButton    = Gtk.Template.Child()
    tab_history:              Gtk.ToggleButton    = Gtk.Template.Child()
    sidebar_stack:            Gtk.Stack           = Gtk.Template.Child()
    spinner:                  Adw.Spinner         = Gtk.Template.Child()
    extract_status_label:     Gtk.Label           = Gtk.Template.Child()
    engine_update_banner:     Adw.Banner          = Gtk.Template.Child()

    # Language selectors
    lang_combo:               Gtk.MenuButton      = Gtk.Template.Child()
    language_popover:         LanguagePopover     = Gtk.Template.Child()
    extra_lang_combo:         Gtk.MenuButton      = Gtk.Template.Child()
    extra_language_popover:   LanguagePopover     = Gtk.Template.Child()
    manage_languages_btn:     Gtk.MenuButton      = Gtk.Template.Child()
    manage_languages_popover: ManageLanguagesPopover = Gtk.Template.Child()

    # Settings controls
    autocopy_switch:          Gtk.Switch          = Gtk.Template.Child()
    autolinks_switch:         Gtk.Switch          = Gtk.Template.Child()
    delete_screenshot_switch: Gtk.Switch          = Gtk.Template.Child()
    hide_during_capture_switch: Gtk.Switch        = Gtk.Template.Child()
    history_days_spin:        Gtk.SpinButton      = Gtk.Template.Child()
    hotkey_capture_btn:       Gtk.Button          = Gtk.Template.Child()
    hotkey_mode_dropdown:     Gtk.DropDown        = Gtk.Template.Child()
    hotkey_clear_btn:         Gtk.Button          = Gtk.Template.Child()
    ocr_engine_dropdown:      Gtk.DropDown        = Gtk.Template.Child()
    ocr_engine_description_label: Gtk.Label       = Gtk.Template.Child()
    ocr_download_box:         Gtk.Box             = Gtk.Template.Child()
    ocr_status_label:         Gtk.Label           = Gtk.Template.Child()
    ocr_action_btn:           Gtk.Button          = Gtk.Template.Child()
    ocr_progress_bar:         Gtk.ProgressBar     = Gtk.Template.Child()

    # Content area
    split_view:               Adw.OverlaySplitView = Gtk.Template.Child()
    content_overlay:          Gtk.Overlay         = Gtk.Template.Child()
    content_stack:            Gtk.Stack           = Gtk.Template.Child()
    text_view:                Gtk.TextView        = Gtk.Template.Child()
    buffer:                   Gtk.TextBuffer      = Gtk.Template.Child()

    # History panel
    history_list:             Gtk.ListBox         = Gtk.Template.Child()
    history_open_btn:         Gtk.Button          = Gtk.Template.Child()
    history_clear_all_btn:    Gtk.Button          = Gtk.Template.Child()

    # ------------------------------------------------------------------ #
    # Initialisation                                                       #
    # ------------------------------------------------------------------ #

    def __init__(self, version: str | None = None, **kwargs):
        super().__init__(**kwargs)

        self.version = version
        self._open_file_dlg: Gtk.FileDialog | None = None
        self.settings = Gtk.Application.get_default().props.settings

        self._init_header(version)
        self._init_language_selectors()
        self._init_settings_bindings()
        self._init_ocr_engine()
        self._init_history()
        self._init_hotkey()
        self._init_screenshot_backend()
        self._init_clipboard()
        self._init_drag_and_drop()
        self._init_window_size()
        self._was_visible_before_capture = True
        self._capture_timeout_id = 0

        self.tab_lens.connect("toggled", self._on_tab_toggled)
        self.tab_settings.connect("toggled", self._on_tab_toggled)
        self.tab_history.connect("toggled", self._on_tab_toggled)

        self.content_stack.set_visible_child_name("empty")

        # Give the window a moment to settle before hitting the network.
        GLib.timeout_add_seconds(3, self._check_engine_updates)

    def _init_header(self, version: str | None) -> None:
        self.app_icon.set_from_resource(f"{RESOURCE_PREFIX}/icons/icon.svg")
        if version:
            self.version_label.set_label(version)

    def _init_language_selectors(self) -> None:
        language_manager.active_language = language_manager.get_language_item(
            self.settings.get_string("active-language")
        )
        self.lang_combo.set_label(
            language_manager.get_language(self.settings.get_string("active-language"))
        )
        self.language_popover.connect("language-changed", self._on_language_changed)

        extra_lang = language_manager.get_language(self.settings.get_string("extra-language"))
        self.extra_lang_combo.set_label(extra_lang or _("None"))
        self.extra_language_popover.connect("language-changed", self._on_extra_language_changed)
        self.extra_language_popover._set_active = False
        self.manage_languages_btn.set_label(_("Download / Remove"))

    def _init_settings_bindings(self) -> None:
        self.settings.bind("autocopy",  self.autocopy_switch,  "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("autolinks", self.autolinks_switch, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("delete-screenshot", self.delete_screenshot_switch, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("hide-during-capture", self.hide_during_capture_switch, "active", Gio.SettingsBindFlags.DEFAULT)

    def _init_screenshot_backend(self) -> None:
        self.backend = ScreenshotService()
        self.backend.connect("text-ready", self._on_text_ready)
        self.backend.connect("error",      self._on_backend_error)

    def _init_clipboard(self) -> None:
        clipboard_service.connect("image-ready", self._on_clipboard_image_ready)
        clipboard_service.connect("error",       self._on_display_error)

    def _init_drag_and_drop(self) -> None:
        drop = Gtk.DropTarget.new(type=Gdk.FileList, actions=Gdk.DragAction.COPY)
        drop.connect("drop",  self._on_dnd_drop)
        drop.connect("enter", self._on_dnd_enter)
        drop.connect("leave", self._on_dnd_leave)
        self.add_controller(drop)

    def _init_window_size(self) -> None:
        saved_w = self.settings.get_int("window-width")
        saved_h = self.settings.get_int("window-height")
        self.props.default_width  = saved_w if saved_w > 0 else 800
        self.props.default_height = saved_h if saved_h > 0 else 605

    # ------------------------------------------------------------------ #
    # Tab switching                                                        #
    # ------------------------------------------------------------------ #

    def _on_tab_toggled(self, _btn: Gtk.ToggleButton) -> None:
        if self.tab_lens.get_active():
            name = "lens"
        elif self.tab_settings.get_active():
            name = "settings"
        else:
            name = "history"
        self.sidebar_stack.set_visible_child_name(name)

    # ------------------------------------------------------------------ #
    # Language                                                             #
    # ------------------------------------------------------------------ #

    def _on_language_changed(self, _, language) -> None:
        self.lang_combo.set_label(language.title)
        self.settings.set_string("active-language", language.code)
        self.settings.sync()

    def _on_extra_language_changed(self, _, language) -> None:
        self.extra_lang_combo.set_label(language.title)
        self.settings.set_string("extra-language", language.code)
        self.settings.sync()

    def _get_lang(self) -> str:
        """Return the active Tesseract language string, e.g. ``"eng+fra"``."""
        active = language_manager.active_language.code
        extra  = self.settings.get_string("extra-language")
        if extra and extra != active:
            return f"{active}+{extra}"
        return active

    def _current_engine(self) -> str:
        """Return the key of the engine chosen in the dropdown."""
        return ENGINE_KEYS[self.ocr_engine_dropdown.get_selected()]

    # Keep old name so main.py callers still work
    def get_language(self) -> str:
        return self._get_lang()

    # ------------------------------------------------------------------ #
    # Screenshot / image extraction                                        #
    # ------------------------------------------------------------------ #

    def _extracting_message(self, engine: str) -> str:
        if engine == "tesseract":
            return _("Decoding your image, please wait…")
        label = ENGINES[engine]["label"]
        return _("{}: Decoding your image, please wait…").format(label)

    def _start_extracting(self, engine: str) -> None:
        self.extract_status_label.set_label(self._extracting_message(engine))
        self.extract_status_label.set_visible(True)
        self.spinner.set_visible(True)

    def _stop_extracting(self) -> None:
        self.spinner.set_visible(False)
        self.extract_status_label.set_visible(False)
        if getattr(self, "_capture_timeout_id", 0):
            GLib.source_remove(self._capture_timeout_id)
            self._capture_timeout_id = 0
        # Undo the minimize() from get_screenshot() — but only if we're
        # the ones who hid it. Leaves the silent global-hotkey path
        # (which never shows the window) untouched, and is a harmless
        # no-op for paths that never hid it (open file, paste, drag-drop).
        # Note: GNOME's Wayland focus-stealing prevention means this may
        # surface as a "Lens is ready" notification rather than actually
        # raising the window — click it to bring Lens forward.
        if getattr(self, "_was_visible_before_capture", True):
            self.present()

    def get_screenshot(self, copy: bool = False) -> None:
        """Trigger the interactive screenshot selector and extract text."""
        engine = self._current_engine()
        self._start_extracting(engine)
        # Only hide/restore if the window was already on screen and the
        # user hasn't turned this off — the silent global-hotkey path
        # never presents the window at all, and should stay that way.
        self._was_visible_before_capture = (
            self.get_visible() and self.settings.get_boolean("hide-during-capture")
        )
        if self._was_visible_before_capture:
            self.minimize()
            # minimize() under Wayland just requests the compositor hide
            # the window — it isn't instant. Firing the screenshot portal
            # immediately after was racing that, so the window was often
            # still visible during capture. Give it a moment first.
            GLib.timeout_add(200, self._start_capture, engine, copy)
        else:
            self._start_capture(engine, copy)

    def _start_capture(self, engine: str, copy: bool) -> bool:
        self.backend.capture(
            self._get_lang(),
            copy,
            engine,
            self.settings.get_boolean("delete-screenshot"),
        )
        # Safety net: if the portal's screenshot picker gets cancelled
        # (Escape, clicking away) some compositors never call back at
        # all, which would otherwise leave the window stuck minimized
        # forever with nothing to trigger present() again.
        self._capture_timeout_id = GLib.timeout_add_seconds(60, self._on_capture_timeout)
        return False  # one-shot timeout, don't repeat

    def _on_capture_timeout(self) -> bool:
        logger.debug("Screenshot capture timed out — restoring window")
        self._capture_timeout_id = 0
        self._stop_extracting()
        return False

    def _on_text_ready(self, _sender, text: str, copy: bool) -> None:
        """Handle successfully extracted text."""
        try:
            self.buffer.set_text(text)
            self.content_stack.set_visible_child_name("text")
            history_service.add(text)
            self.tab_lens.set_active(True)

            if self.settings.get_boolean("autocopy") or copy:
                clipboard_service.set(text)
                self.show_toast(_("Text copied to clipboard"))

            if self.uri_validator(text):
                if self.settings.get_boolean("autolinks"):
                    Gtk.UriLauncher.new(text).launch()
                    self.show_toast(_("QR-code URL opened"), priority=Adw.ToastPriority.HIGH)
                else:
                    toast = Adw.Toast(
                        title=_("QR-code contains URL."),
                        button_label=_("Open"),
                        priority=Adw.ToastPriority.HIGH,
                    )
                    toast.set_detailed_action_name(f'app.show_uri("{text}")')
                    self.toast_overlay.add_toast(toast)

        except Exception as exc:
            logger.debug(f"on_text_ready error: {exc}")
        finally:
            self._stop_extracting()

    def _on_backend_error(self, _sender, message: str) -> None:
        self._stop_extracting()
        if message and message != "Cancelled":
            self.show_toast(message)

    # ------------------------------------------------------------------ #
    # Open image                                                           #
    # ------------------------------------------------------------------ #

    def open_image(self) -> None:
        """Show a file-chooser dialog and extract text from the chosen image."""
        self._open_file_dlg = Gtk.FileDialog()

        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        f.set_name(_("Image files"))
        for mime in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
            f.add_mime_type(mime)
        filters.append(f)

        self._open_file_dlg.set_title(_("Open image to extract text"))
        self._open_file_dlg.set_filters(filters)
        self._open_file_dlg.open(self, None, self._on_image_chosen)

    def _on_image_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            item = dialog.open_finish(result)
            engine = self._current_engine()
            self._start_extracting(engine)
            GObjectWorker.call(
                self.backend.decode_image,
                (self._get_lang(), item.get_path(), False, False, engine),
            )
        except GLib.Error as exc:
            if not exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                logger.debug(exc)

    # ------------------------------------------------------------------ #
    # Clipboard paste                                                      #
    # ------------------------------------------------------------------ #

    def on_paste_from_clipboard(self, _sender) -> None:
        """Request an image read from the system clipboard."""
        clipboard_service.read_image()

    def _on_clipboard_image_ready(self, _svc: ClipboardService, texture: Gdk.Texture) -> None:
        buf = BytesIO(texture.save_to_png_bytes().get_data())
        try:
            engine = self._current_engine()
            self._start_extracting(engine)
            GObjectWorker.call(
                self.backend.decode_image,
                (self._get_lang(), buf, False, False, engine),
            )
        except GLib.Error as exc:
            if not exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                logger.debug(exc)

    # ------------------------------------------------------------------ #
    # Copy extracted text                                                  #
    # ------------------------------------------------------------------ #

    def on_copy_to_clipboard(self, _sender) -> None:
        text = self.buffer.get_text(
            self.buffer.get_start_iter(),
            self.buffer.get_end_iter(),
            False,
        )
        if text:
            clipboard_service.set(text)
            self.show_toast(_("Text copied"))

    # ------------------------------------------------------------------ #
    # Drag-and-drop                                                        #
    # ------------------------------------------------------------------ #

    def _on_dnd_enter(self, _drop, _x, _y):
        self.add_css_class("drop_hover")
        return Gdk.DragAction.COPY

    def _on_dnd_leave(self, *_) -> None:
        self.remove_css_class("drop_hover")

    def _on_dnd_drop(self, _drop, value: Gdk.FileList, _x: int, _y: int) -> None:
        files = value.get_files()
        if not files:
            return
        item = files[0]
        mime, _ = guess_type(item.get_path())
        logger.debug(f"DnD drop: {mime} — {item.get_path()}")
        if not mime or not mime.startswith("image"):
            self.show_toast(_("Only images can be processed that way."))
            return
        engine = self._current_engine()
        self._start_extracting(engine)
        GObjectWorker.call(
            self.backend.decode_image,
            (self._get_lang(), item.get_path(), False, False, engine),
        )

    # ------------------------------------------------------------------ #
    # History panel                                                        #
    # ------------------------------------------------------------------ #

    def _init_ocr_engine(self) -> None:
        """Initialise OCR engine selector."""
        saved = self.settings.get_string("ocr-engine")
        idx = ENGINE_KEYS.index(saved) if saved in ENGINE_KEYS else 0
        self.ocr_engine_dropdown.set_selected(idx)
        self.ocr_engine_dropdown.connect("notify::selected", self._on_ocr_engine_changed)

        # Descriptions for each engine option — shown in the card and
        # doubled up as the dropdown's hover tooltip.
        descriptions = [
            _("Default engine. Fast, offline, 100+ languages. Best for clean printed text."),
            _("Tiny and instant, no download. Latin-script printed text only, no language packs."),
            _("Better accuracy on photos, handwriting and complex backgrounds. Requires download (~2.5 GB)."),
            _("Best for structured documents and multi-column layouts. Requires download (~2 GB)."),
        ]
        self._ocr_descriptions = descriptions
        self._ocr_downloading = False
        self._ocr_pulse_id = 0
        self._downloading_engine: str | None = None
        self._pending_updates: dict[str, str] = {}
        self._banner_engine: str | None = None
        self._current_engine_installed = False
        self.ocr_engine_dropdown.set_tooltip_text(descriptions[idx])
        self.ocr_engine_description_label.set_label(descriptions[idx])
        self.ocr_action_btn.connect("clicked", self._on_ocr_action_clicked)
        self.engine_update_banner.connect("button-clicked", self._on_engine_update_clicked)
        ocr_engine_service.connect("download-progress", self._on_ocr_download_progress)
        ocr_engine_service.connect("download-done",     self._on_ocr_download_done)
        ocr_engine_service.connect("uninstall-done",    self._on_ocr_uninstall_done)
        ocr_engine_service.connect("engine-fallback",   self._on_ocr_fallback)
        ocr_engine_service.connect("update-available",  self._on_engine_update_available)
        self._update_ocr_status()

    def _on_ocr_engine_changed(self, dropdown, _param) -> None:
        idx = dropdown.get_selected()
        engine = ENGINE_KEYS[idx]
        self.settings.set_string("ocr-engine", engine)
        self.settings.sync()
        self.ocr_engine_dropdown.set_tooltip_text(self._ocr_descriptions[idx])
        self.ocr_engine_description_label.set_label(self._ocr_descriptions[idx])
        self._update_ocr_status()

    def _update_ocr_status(self) -> None:
        """
        Refresh the action button and download row for the selected engine.

        The installed check talks to the host over D-Bus, so it runs on
        a worker thread and the result is applied back on the main loop.
        """
        if self._ocr_downloading:
            return
        engine = self._current_engine()
        self.ocr_action_btn.set_visible(False)
        GObjectWorker.call(
            ocr_engine_service.is_installed,
            (engine,),
            lambda installed: self._apply_ocr_status(engine, installed),
        )

    def _apply_ocr_status(self, engine: str, installed: bool) -> None:
        # The user may have switched engines while the check ran.
        if engine != self._current_engine() or self._ocr_downloading:
            return
        logger.debug(f"OCR engine: {engine}, installed: {installed}")
        self._current_engine_installed = installed

        if engine in BUILTIN_ENGINES:
            self.ocr_action_btn.set_visible(False)
            self.ocr_download_box.set_visible(False)
            return

        if installed:
            self.ocr_action_btn.set_visible(True)
            self.ocr_action_btn.set_icon_name("user-trash-symbolic")
            self.ocr_action_btn.set_tooltip_text(_("Remove this engine from disk"))
            self.ocr_download_box.set_visible(False)
        else:
            label = ENGINES[engine]["label"]
            self.ocr_action_btn.set_visible(True)
            self.ocr_action_btn.set_icon_name("folder-download-symbolic")
            self.ocr_action_btn.set_tooltip_text(_("Download {}").format(label))
            self.ocr_status_label.set_label(_("{} is not installed.").format(label))
            self.ocr_download_box.set_visible(True)
            self.ocr_progress_bar.set_visible(False)

    def _on_ocr_action_clicked(self, _btn) -> None:
        if self._current_engine_installed:
            self._on_ocr_uninstall(_btn)
        else:
            self._on_ocr_download(_btn)

    def _on_ocr_download(self, _btn) -> None:
        self._begin_engine_download(self._current_engine())

    def _begin_engine_download(self, engine: str) -> None:
        """Kick off an install/upgrade for *engine* (used by both the
        Settings page action button and the update banner)."""
        logger.debug(f"Starting download of engine: {engine}")
        self._downloading_engine = engine
        if engine == self._current_engine():
            self._ocr_downloading = True
            self.ocr_action_btn.set_sensitive(False)
            self.ocr_engine_dropdown.set_sensitive(False)
            self.ocr_download_box.set_visible(True)
            self.ocr_status_label.set_label(_("Starting download…"))
            self.ocr_progress_bar.set_visible(True)
            self._ocr_pulse_id = GLib.timeout_add(120, self._ocr_pulse)
        ocr_engine_service.install(engine)

    def _ocr_pulse(self) -> bool:
        self.ocr_progress_bar.pulse()
        return True

    def _stop_ocr_pulse(self) -> None:
        if self._ocr_pulse_id:
            GLib.source_remove(self._ocr_pulse_id)
            self._ocr_pulse_id = 0
        self.ocr_progress_bar.set_visible(False)

    def _on_ocr_download_progress(self, _svc, msg: str) -> None:
        if self._downloading_engine == self._current_engine():
            self.ocr_status_label.set_label(msg)

    def _on_ocr_download_done(self, _svc, success: bool) -> None:
        engine = self._downloading_engine
        self._downloading_engine = None

        if engine == self._current_engine():
            self._ocr_downloading = False
            self._stop_ocr_pulse()
            self.ocr_action_btn.set_sensitive(True)
            self.ocr_engine_dropdown.set_sensitive(True)
            if not success:
                self.ocr_status_label.set_label(_("Download failed. Check your connection."))
            self._update_ocr_status()

        if engine:
            label = ENGINES[engine]["label"]
            if engine != self._current_engine():
                self.show_toast(
                    _("{} is ready").format(label) if success
                    else _("Could not update {}").format(label)
                )
            elif success:
                self.show_toast(_("{} is ready").format(label))

        # Whether this run came from the banner or not, move the queue on.
        self._banner_engine = None
        self._show_next_update_banner()

    # ------------------------------------------------------------------ #
    # Engine update checking                                              #
    # ------------------------------------------------------------------ #

    def _check_engine_updates(self) -> bool:
        ocr_engine_service.check_updates()
        return False  # one-shot timeout

    def _on_engine_update_available(self, _svc, engine: str, latest_version: str) -> None:
        self._pending_updates[engine] = latest_version
        if not self._banner_engine:
            self._show_next_update_banner()

    def _show_next_update_banner(self) -> None:
        if not self._pending_updates:
            self.engine_update_banner.set_revealed(False)
            self._banner_engine = None
            return
        engine, version = next(iter(self._pending_updates.items()))
        self._banner_engine = engine
        label = ENGINES[engine]["label"]
        self.engine_update_banner.set_title(
            _("{} update available — v{}").format(label, version)
        )
        self.engine_update_banner.set_revealed(True)

    def _on_engine_update_clicked(self, _banner) -> None:
        engine = self._banner_engine
        if not engine:
            return
        self._pending_updates.pop(engine, None)
        self.engine_update_banner.set_revealed(False)
        label = ENGINES[engine]["label"]
        self.show_toast(_("Updating {}…").format(label))
        self._begin_engine_download(engine)

    def _on_ocr_uninstall(self, _btn) -> None:
        engine = self._current_engine()
        label = ENGINES[engine]["label"]
        dialog = Adw.AlertDialog(
            heading=_("Remove {}?").format(label),
            body=_("The engine will be deleted from disk. You can download it again at any time."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_ocr_uninstall_response, engine)
        dialog.present(self)

    def _on_ocr_uninstall_response(self, _dialog, response: str, engine: str) -> None:
        if response != "remove":
            return
        self.ocr_action_btn.set_sensitive(False)
        ocr_engine_service.uninstall(engine)

    def _on_ocr_uninstall_done(self, _svc, success: bool) -> None:
        self.ocr_action_btn.set_sensitive(True)
        self.show_toast(
            _("OCR engine removed") if success else _("Could not remove engine")
        )
        self._update_ocr_status()

    def _on_ocr_fallback(self, _svc, label: str) -> None:
        self.show_toast(
            _("{} failed — used Tesseract instead").format(label),
            timeout=4,
        )

    def _init_history(self) -> None:
        history_service.connect("changed", self._on_history_changed)

        days = self.settings.get_int("history-days")
        self.history_days_spin.set_value(days)
        self.history_days_spin.connect("value-changed", self._on_history_days_changed)
        history_service.purge_old(days)

        self.history_open_btn.connect("clicked", self._on_history_open_clicked)
        self.history_clear_all_btn.connect("clicked", self._on_history_clear_all)

        self._refresh_history()

    def _on_history_open_clicked(self, _btn) -> None:
        self.tab_history.set_active(True)

    def _on_history_days_changed(self, spin: Gtk.SpinButton) -> None:
        days = int(spin.get_value())
        self.settings.set_int("history-days", days)
        self.settings.sync()
        history_service.purge_old(days)

    def _refresh_history(self) -> None:
        # Disconnect old row-selected signal to avoid duplicates
        try:
            self.history_list.disconnect_by_func(self._on_history_row_selected)
        except Exception:
            pass

        while row := self.history_list.get_row_at_index(0):
            self.history_list.remove(row)

        for entry in history_service.entries():
            self.history_list.append(self._make_history_row(entry))

        self.history_list.connect("row-selected", self._on_history_row_selected)

    def _make_history_row(self, entry: HistoryEntry) -> Gtk.ListBoxRow:
        row          = Gtk.ListBoxRow()
        row.entry_id = entry.id
        row.entry_text = entry.text
        # The row itself is the visual card — one widget, one
        # background — rather than a child box with the row's own
        # default background potentially showing through around it.
        row.add_css_class("history-entry-card")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(6)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text_box.set_hexpand(True)

        time_lbl = Gtk.Label(label=entry.friendly_time(), xalign=0)
        time_lbl.add_css_class("caption")
        time_lbl.add_css_class("dim-label")

        prev_lbl = Gtk.Label(label=entry.preview(), xalign=0)
        prev_lbl.add_css_class("caption")
        prev_lbl.set_ellipsize(3)
        prev_lbl.set_max_width_chars(20)

        text_box.append(time_lbl)
        text_box.append(prev_lbl)
        box.append(text_box)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic", has_frame=False)
        del_btn.add_css_class("flat")
        del_btn.add_css_class("history-del-btn")
        del_btn.set_tooltip_text(_("Delete this entry"))
        del_btn.connect("clicked", self._on_history_delete, entry.id)
        box.append(del_btn)

        row.set_child(box)
        return row

    def _on_history_row_selected(self, _listbox, row) -> None:
        if row:
            self.buffer.set_text(row.entry_text)
            self.content_stack.set_visible_child_name("text")

    def _on_history_delete(self, _btn, entry_id: str) -> None:
        history_service.delete(entry_id)

    def _on_history_clear_all(self, _btn) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Delete all history?"),
            body=_("This cannot be undone."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete All"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect(
            "response",
            lambda d, r: history_service.clear() if r == "delete" else None,
        )
        dialog.present(self)

    def _on_history_changed(self, _) -> None:
        self._refresh_history()

    # ------------------------------------------------------------------ #
    # Global hotkey                                                        #
    # ------------------------------------------------------------------ #

    def _init_hotkey(self) -> None:
        """Wire up the system-wide shortcut controls in Settings."""
        self._hotkey_capturing = False
        self._hotkey_key_controller: Gtk.EventControllerKey | None = None

        self.hotkey_mode_dropdown.set_model(
            Gtk.StringList.new([_("Open Lens"), _("Copy text silently")])
        )
        self.hotkey_capture_btn.connect("clicked", self._on_hotkey_capture_clicked)
        self.hotkey_clear_btn.connect("clicked", self._on_hotkey_clear_clicked)
        self.hotkey_mode_dropdown.connect("notify::selected", self._on_hotkey_mode_changed)

        self._refresh_hotkey_status()

    def _refresh_hotkey_status(self) -> None:
        """Read the current shortcut/mode off the host — do it off-thread."""
        GObjectWorker.call(
            lambda: (hotkey_service.get_current_shortcut(), hotkey_service.get_current_mode()),
            callback=self._apply_hotkey_status,
        )

    def _apply_hotkey_status(self, result: tuple[str | None, str]) -> None:
        shortcut, mode = result
        if shortcut:
            ok, keyval, mods = Gtk.accelerator_parse(shortcut)
            label = Gtk.accelerator_get_label(keyval, mods) if ok else shortcut
            self.hotkey_capture_btn.set_label(label)
            self.hotkey_clear_btn.set_sensitive(True)
            self.hotkey_mode_dropdown.set_sensitive(True)
            self.hotkey_mode_dropdown.set_selected(1 if mode == "silent" else 0)
        else:
            self.hotkey_capture_btn.set_label(_("Set Shortcut"))
            self.hotkey_clear_btn.set_sensitive(False)
            self.hotkey_mode_dropdown.set_sensitive(False)

    def _on_hotkey_capture_clicked(self, _btn) -> None:
        if self._hotkey_capturing:
            return
        self._hotkey_capturing = True
        self.hotkey_capture_btn.set_label(_("Press a key combination… (Esc to cancel)"))

        controller = Gtk.EventControllerKey.new()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_hotkey_key_pressed)
        self.add_controller(controller)
        self._hotkey_key_controller = controller

    def _stop_hotkey_capture(self) -> None:
        self._hotkey_capturing = False
        if self._hotkey_key_controller:
            self.remove_controller(self._hotkey_key_controller)
            self._hotkey_key_controller = None

    def _on_hotkey_key_pressed(self, _controller, keyval, _keycode, state) -> bool:
        if not self._hotkey_capturing:
            return False

        if keyval == Gdk.KEY_Escape:
            self._stop_hotkey_capture()
            self._refresh_hotkey_status()
            return True

        # Ignore bare modifier presses — wait for the real key.
        if keyval in (
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
            Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L, Gdk.KEY_Super_R,
        ):
            return True

        mods = state & Gtk.accelerator_get_default_mod_mask()
        if not mods:
            # Require at least one modifier so plain letters still type normally.
            self.show_toast(_("Include Ctrl, Alt, or Super in the shortcut"))
            return True

        binding = Gtk.accelerator_name(keyval, mods)
        self._stop_hotkey_capture()

        self.hotkey_capture_btn.set_label(_("Checking…"))
        GObjectWorker.call(
            lambda: hotkey_service.find_conflict(binding),
            callback=lambda conflict: self._on_hotkey_conflict_checked(binding, conflict),
        )
        return True

    def _on_hotkey_conflict_checked(self, binding: str, conflict: str | None) -> None:
        if conflict:
            ok, keyval, mods = Gtk.accelerator_parse(binding)
            display = Gtk.accelerator_get_label(keyval, mods) if ok else binding
            dialog = Adw.AlertDialog(
                heading=_("Shortcut Already in Use"),
                body=_(
                    "{shortcut} is already used by “{other}”. Setting it here "
                    "may stop that shortcut from working."
                ).format(shortcut=display, other=conflict),
            )
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("use", _("Use Anyway"))
            dialog.set_response_appearance("use", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_hotkey_conflict_response, binding)
            dialog.present(self)
        else:
            self._save_hotkey(binding)

    def _on_hotkey_conflict_response(self, _dialog, response: str, binding: str) -> None:
        if response == "use":
            self._save_hotkey(binding)
        else:
            self._refresh_hotkey_status()

    def _save_hotkey(self, binding: str) -> None:
        mode = "silent" if self.hotkey_mode_dropdown.get_selected() == 1 else "show"
        self.hotkey_capture_btn.set_label(_("Saving…"))
        GObjectWorker.call(
            lambda: hotkey_service.set_shortcut(binding, mode),
            callback=lambda ok: self._on_hotkey_set_done(ok, binding),
        )

    def _on_hotkey_set_done(self, ok: bool, binding: str) -> None:
        if ok:
            self.show_toast(_("Shortcut updated"))
        else:
            self.show_toast(_("Couldn't set that shortcut"))
        self._refresh_hotkey_status()

    def _on_hotkey_clear_clicked(self, _btn) -> None:
        self.hotkey_clear_btn.set_sensitive(False)
        GObjectWorker.call(
            hotkey_service.clear_shortcut,
            callback=self._on_hotkey_clear_done,
        )

    def _on_hotkey_clear_done(self, ok: bool) -> None:
        self.show_toast(_("Shortcut removed") if ok else _("Couldn't remove shortcut"))
        self._refresh_hotkey_status()

    def _on_hotkey_mode_changed(self, dropdown, _param) -> None:
        # Only re-save if a shortcut already exists — otherwise this fires
        # on startup with nothing to apply yet.
        if not self.hotkey_clear_btn.get_sensitive():
            return
        GObjectWorker.call(
            lambda: (hotkey_service.get_current_shortcut(),),
            callback=lambda result: self._reapply_hotkey_mode(result[0]),
        )

    def _reapply_hotkey_mode(self, shortcut: str | None) -> None:
        if not shortcut:
            return
        mode = "silent" if self.hotkey_mode_dropdown.get_selected() == 1 else "show"
        GObjectWorker.call(lambda: hotkey_service.set_shortcut(shortcut, mode))

    # ------------------------------------------------------------------ #
    # Error display                                                        #
    # ------------------------------------------------------------------ #

    def _on_display_error(self, _sender, error) -> None:
        msg = str(error).split(":")[-1] if not isinstance(error, str) else error
        self.show_toast(msg)

    # ------------------------------------------------------------------ #
    # Window lifecycle                                                     #
    # ------------------------------------------------------------------ #

    def do_close_request(self) -> bool:
        w, h = self.get_default_size()
        self.settings.set_int("window-width",  w)
        self.settings.set_int("window-height", h)
        self.settings.sync()
        return False

    # ------------------------------------------------------------------ #
    # Public helpers                                                       #
    # ------------------------------------------------------------------ #

    def clear_text(self) -> None:
        """Clear the text view and return to empty state."""
        self.buffer.set_text("")
        self.content_stack.set_visible_child_name("empty")

    def show_toast(
        self,
        title: str,
        timeout: int = 2,
        priority: Adw.ToastPriority = Adw.ToastPriority.NORMAL,
    ) -> None:
        self.toast_overlay.add_toast(
            Adw.Toast(title=title, timeout=timeout, priority=priority)
        )

    def uri_validator(self, link: str) -> bool:
        try:
            r = urlparse(link)
            return bool(r.scheme and r.netloc)
        except Exception:
            return False
