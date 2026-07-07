"""batplot: Interactive plotting for battery data visualization."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

__version__ = "1.8.46"


_LEGACY_MODULE_ALIASES = {
    "batplot.interactive": "batplot.plot_modes.xy.interactive",
    "batplot.electrochem_interactive": "batplot.plot_modes.electrochem.interactive",
    "batplot.cpc_interactive": "batplot.plot_modes.cpc.interactive",
    "batplot.cpc_menu": "batplot.plot_modes.cpc.menu",
    "batplot.operando_ec_interactive": "batplot.plot_modes.operando.interactive",
    "batplot.operando_layout": "batplot.plot_modes.operando.layout",
    "batplot.operando_menu": "batplot.plot_modes.operando.menu",
    "batplot.operando_style": "batplot.plot_modes.operando.style",
    "batplot.interactive_state": "batplot.plot_modes.common.interactive_state",
}


class _LegacyModuleAliasLoader(importlib.abc.Loader):
    """Lazy compatibility loader for mode modules moved under ``plot_modes``."""

    def __init__(self, fullname: str, target_name: str):
        self.fullname = fullname
        self.target_name = target_name

    def create_module(self, spec):
        module = importlib.import_module(self.target_name)
        self._apply_extra_exports(module)
        sys.modules[self.fullname] = module
        parent_name, _, child_name = self.fullname.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, module)
        return module

    def exec_module(self, module) -> None:
        return None

    def _apply_extra_exports(self, module) -> None:
        if self.fullname == "batplot.cpc_interactive":
            menu = importlib.import_module("batplot.plot_modes.cpc.menu")
            module.print_cpc_menu = menu.print_cpc_menu
            module.build_cpc_menu_columns = menu.build_cpc_menu_columns
        elif self.fullname == "batplot.operando_ec_interactive":
            style = importlib.import_module("batplot.plot_modes.operando.style")
            module.build_operando_ec_style_config_v2 = style.build_operando_ec_style_config_v2


class _LegacyModuleAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        target_name = _LEGACY_MODULE_ALIASES.get(fullname)
        if target_name is None:
            return None
        loader = _LegacyModuleAliasLoader(fullname, target_name)
        spec = importlib.machinery.ModuleSpec(fullname, loader)
        spec.origin = f"legacy-alias:{target_name}"
        return spec


def _install_legacy_alias_finder() -> None:
    if not any(isinstance(finder, _LegacyModuleAliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _LegacyModuleAliasFinder())


_install_legacy_alias_finder()

__all__ = ["__version__"]
