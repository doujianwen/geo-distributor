"""Immutable Versioning Red-Team — Phase 6

攻击版本修改、删除、覆盖、collision 等场景。
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from geo_distributor.models.geo_core import Report, ReportType


class TestVersionIntegrity:
    """版本不可变性攻击测试。"""

    def test_version_appended_not_overwritten(self):
        """新版本应追加，不覆盖旧版本。"""
        r = Report(
            report_id="RPT-VER-001",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        r.add_version({"summary": "v1 content"}, is_client_safe=True, notes="v1")
        r.add_version({"summary": "v2 content"}, is_client_safe=True, notes="v2")

        assert len(r.versions) == 2
        assert r.versions[0].version == 1
        assert r.versions[0].content["summary"] == "v1 content"
        assert r.versions[1].version == 2
        assert r.versions[1].content["summary"] == "v2 content"

    def test_old_version_unaffected_by_new(self):
        """新版本不应影响旧版本内容。"""
        r = Report(
            report_id="RPT-VER-002",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        r.add_version({"data": "original"}, is_client_safe=True)
        original_v1 = r.versions[0].content.copy()

        r.add_version({"data": "modified"}, is_client_safe=True)

        assert r.versions[0].content["data"] == "original"
        assert r.versions[1].content["data"] == "modified"

    def test_version_number_increasing(self):
        """版本号必须递增。"""
        r = Report(
            report_id="RPT-VER-003",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        r.add_version({"v": 1})
        r.add_version({"v": 2})
        r.add_version({"v": 3})

        versions = [v.version for v in r.versions]
        assert versions == [1, 2, 3]

    def test_get_latest_returns_highest_version(self):
        """get_latest_version 应返回最新版本。"""
        r = Report(
            report_id="RPT-VER-004",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        r.add_version({"content": "v1"})
        r.add_version({"content": "v2"})
        r.add_version({"content": "v3"})

        latest = r.get_latest_version()
        assert latest.version == 3
        assert latest.content["content"] == "v3"

    def test_no_version_collision(self):
        """不存在版本号碰撞。"""
        r = Report(
            report_id="RPT-VER-005",
            project_id="PRJ-001",
            tenant_id="DST-001",
            type=ReportType.CLIENT,
        )
        r.add_version({"v": 1})
        r.add_version({"v": 1})  # 尝试创建相同版本

        # 应该创建 v2，而不是覆盖 v1
        assert len(r.versions) == 2
        assert r.versions[0].version == 1
        assert r.versions[1].version == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
