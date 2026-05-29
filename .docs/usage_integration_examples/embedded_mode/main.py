# examples/embedded_mode/main.py
"""
Embedded Pattern Composition Root.
يشغّل FabricClient و BaseActor في نفس العملية.
مثالي للخدمات المستقلة، الـ Microservices، أو وكلاء الذكاء الاصطناعي.
"""
from __future__ import annotations
import asyncio
import logging
from wiring.runner import AppRunner
from actors.base_actor import BaseActor
from contracts.communication_gateway import ICommunicationGateway

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")

async def main():
    # 1. تشغيل الفابريك (يملك FabricClient داخليًا)
    runner = AppRunner("config/transport_example.yaml")
    asyncio.create_task(runner.start())  # تشغيل في الخلفية
    
    # انتظار جاهزية النظام
    await asyncio.sleep(2)
    
    # 2. حقن الواجهة للوكيل (DIP صريح)
    actor = BaseActor(gateway=runner.fabric_client, actor_id="embedded-agent")
    
    try:
        # 3. تفاعل عملي
        result = await actor.execute_task(
            payload={"action": "analyze", "data": "system_metrics.json"},
            protocol="http"
        )
        print(f"✅ Task Result: {result}")
        
        # 4. فحص الصحة
        health = await runner.fabric_client.health_check()
        print(f"📊 Fabric Health: {health['status']} | Pipelines: {health['active_pipelines']}")
        
    finally:
        await actor.close()
        await runner.stop()

if __name__ == "__main__":
    asyncio.run(main())