"""Benchmark 测试 fixtures。

项目级 fixtures (db_session, test_client, mock_provider) 定义在
tests/conftest.py 中。pytest 会通过 conftest 继承机制自动向子目录注入，
因此 benchmark 目录下的测试无需任何显式导入即可使用这些 fixtures。

本文件保留为 benchmark 目录的 fixture 扩展点，后续可在此添加压测专用
fixtures (例如批量记忆注入、LLM mock 池、压测数据快照等)。
"""

# db_session / test_client / mock_provider 由 tests/conftest.py 自动注入。
# 如需 benchmark 专用 fixture，在下方扩展即可，例如:
#
# @pytest.fixture(scope="session")
# def benchmark_dataset():
#     from .data_generator import ConversationGenerator
#     return ConversationGenerator.generate_batch(num_conversations=10)
