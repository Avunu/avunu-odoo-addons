# Copyright 2026 Avunu LLC (avu.nu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import os

from odoo import models


class FsStorage(models.Model):
    _inherit = "fs.storage"

    def get_directory_path(self):
        """Also expand $VARs in the path when the storage reads its env.

        fs_storage only expands environment variables inside ``options``; the
        bucket name lives in ``directory_path``.
        """
        path = super().get_directory_path()
        if self.eval_options_from_env and isinstance(path, str):
            path = os.path.expandvars(path)
        return path
