# examples/gateway_mode/actor_service/main.py
"""
Actor Process (Gateway Pattern).
يعمل في حاوية/عملية منفصلة. يتصل بـ FabricService المركزي عبر RemoteAdapter.
كود BaseActor مطابق 100% للنمط المضمن.
"""
from __future__ import annotations
import asyncio
import logging
from actors.base_actor import BaseActor
from examples.gateway_mode.remote_adapter import RemoteGatewayAdapter

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | [GatewayActor] | %(message)s")

async def main():
    # 1. إنشاء أدابتر بعيد (يطبق نفس العقد!)
    remote_gw = RemoteGatewayAdapter(base_url="http://fabric-service:8000/api/v1")
    
    # 2. نفس كود الوكيل بدون تعديل
    actor = BaseActor(gateway=remote_gw, actor_id="gateway-agent")
    
    try:
        # 3. انتظار جاهزية البوابة المركزية
        for _ in range(10):
            try:
                status = await remote_gw.readiness_check()
                if status["status"] == "ready": break
            except Exception: pass
            await asyncio.sleep(2)
            
        # 4. تنفيذ مهمة عبر البوابة
        result = await actor.execute_task(
            payload={"action": "translate", "text": "Hello Architecture"},
            protocol="graphql"
        )
        print(f"✅ Remote Task Result: {result}")
        
    finally:
        await actor.close()
        await remote_gw.close()

if __name__ == "__main__":
    asyncio.run(main())