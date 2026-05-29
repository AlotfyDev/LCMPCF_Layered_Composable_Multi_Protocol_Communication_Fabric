# main.py
"""
System Entry Point (Composition Root).
يُهيئ البيئة، يشغّل AppRunner، ويعزل منطق الأعمال عن البنية التحتية.
"""
from __future__ import annotations

import asyncio
import logging
import sys

# تكوين السجلات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else "transport_example.yaml"
    
    # نقطة الدخول الوحيدة: AppRunner يملك FabricClient ويدير دورة حياته
    await AppRunner.run(config_file)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Exiting gracefully...")
        sys.exit(0)
        
        
        
"""
[مستخدم يضغط Ctrl+C]
       │
       ▼ (نظام التشغيل يرسل SIGINT)
[AppRunner._on_signal] ← يُفعّل _shutdown_event
       │
       ▼ (حلقة الانتظار تستيقظ)
[AppRunner.stop()] ← ينادي fabric_client.close()
       │
       ▼ (تسلسل الإغلاق العكسي)
FabricClient → PipelineRegistry → LayerRegistry → SessionRegistry → ChannelPool → Sockets
       │
       ▼ (تنظيف كامل)
[AppRunner] ← يُنهي البرنامج برمز خروج 0

"""