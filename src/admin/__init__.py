# ==================================================
# Project Author: Reza Mardani
# Bale ID: @MrHanzo
# GitHub: https://github.com/rezamardani01
#
# This project is open-source and publicly available.
# You are free to use, study, modify, and distribute
# this source code in accordance with its license.
#
# Contributions, improvements, and suggestions are welcome.
# Please give proper credit to the original author
# when using or redistributing this project.
# ==================================================
# -*- coding: utf-8 -*-
"""پنل مدیریت شیشه‌ای: مجموعه روترهای ادمین."""
from baleropy import Router

from . import broadcast, economy, manage, panel, reports, settings, users
from .common import AdminGate

router = Router(name="admin")
router.callback_query.middleware(AdminGate())
router.include_routers(
    panel.router, users.router, reports.router, broadcast.router,
    settings.router, manage.router, economy.router,
)

__all__ = ["router"]
