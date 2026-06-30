"""
结构化错误层级 — Loop Engineering Verify 阶段用
"""


class TRPG2SKILLError(Exception):
    """Base error"""


class ConfigError(TRPG2SKILLError):
    """API 配置缺失或无效"""


class CompileError(TRPG2SKILLError):
    """编译管线错误"""
    def __init__(self, phase: str, message: str):
        self.phase = phase
        super().__init__(f"[{phase}] {message}")


class EngineError(TRPG2SKILLError):
    """运行时引擎错误"""


class LLMError(TRPG2SKILLError):
    """LLM API 调用错误"""
    def __init__(self, message: str, retryable: bool = False):
        self.retryable = retryable
        super().__init__(message)
