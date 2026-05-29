# consumer_example.py
"""
مثال استهلاك تكوين L4 التصريحي.
يوضح: تحميل YAML → تصديق Pydantic → حقن سياسة L5 → بناء الناقل عبر Factory
"""
import yaml
from pathlib import Path
from transport.config import TransportConfig
from transport.context import RetryHook, RetryDecision, TransportContext
from transport.factory import TransportFactory, TransportFactoryError

# 1️⃣ تعريف خطاف سياسة L5 (يُحقن وقت التشغيل، لا يُكتب في YAML)
def l5_retry_hook(
    context: TransportContext,
    error: Exception,
    attempt: int,
    max_attempts: int
) -> RetryDecision:
    """خطاف يقرر سلوك الاستعادة بناءً على حالة الجلسة ونوع الخطأ"""
    err_msg = str(error).lower()
    if "timeout" in err_msg and attempt < max_attempts:
        return "retry"
    if "connection_refused" in err_msg:
        return "restore_checkpoint"
    return "abort"

def build_transporter_from_yaml(config_name: str, yaml_path: str = "transport_example.yaml"):
    """يحمّل التكوين، يتحقق منه، ويبني كومة النقل L4"""
    try:
        # أ) تحميل YAML الخام
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_configs = yaml.safe_load(f)
        if config_name not in raw_configs:
            raise ValueError(f"تكوين '{config_name}' غير موجود في الملف")

        raw_cfg = raw_configs[config_name]

        # ب) التصديق والهيكلة عبر Pydantic v2
        config = TransportConfig.model_validate(raw_cfg)

        # ج) الحقن والتركيب عبر المصنع
        transporter = TransportFactory.create(
            config=config,
            retry_hook=l5_retry_hook
            # يمكن إضافة error_classifier مخصص هنا إذا لزم
        )

        print(f"✅ تم بناء الناقل بنجاح: '{config_name}'")
        print(f"   النوع: {config.transport_type.value}")
        print(f"   الاتجاه: {config.direction}")
        print(f"   retries: {config.retry_policy.max_attempts}")
        return transporter

    except Exception as e:
        print(f"❌ فشل بناء الناقل: {e}")
        raise

if __name__ == "__main__":
    # بناء ناقل CLI
    cli_transporter = build_transporter_from_yaml("cli_coder_agent")
    
    # بناء ناقل A2A
    a2a_transporter = build_transporter_from_yaml("a2a_reviewer_agent")
    