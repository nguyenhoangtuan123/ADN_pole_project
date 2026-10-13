import os
import tempfile
from pathlib import Path

import pytest

# Test dùng cơ sở dữ liệu tạm, không đụng vào database/tru_adn.db thật.
os.environ["ADN_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="adn_test_"), "test.db")


@pytest.fixture
def tmp_path():
    # Ghi đè fixture mặc định của pytest (không tạo được thư mục trong một số máy Windows).
    return Path(tempfile.mkdtemp(prefix="adn_case_"))
