from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Users
from app.constants import UserRoles, BillingType
import asyncio

async def get_users():
    async with AsyncSessionLocal() as db:
        query = select(Users).where(Users.username == "abhishekabck")
        result = await db.execute(query)
        return result.scalars().first()

async def update_user_to_superuser(username):
    async with AsyncSessionLocal() as db:
        query = select(Users).where(Users.username == username)
        result = await db.execute(query)
        model = result.scalars().first()

        if not model:
            print("User not found")
            return

        model.role = UserRoles.ADMIN
        model.billing_type = BillingType.PAID

        await db.commit()           # ✅ IMPORTANT
        await db.refresh(model)     # optional but good

# asyncio.run(update_user_to_superuser("abhishekabck"))

data = asyncio.run(get_users())
print(data.username, data.role, data.billing_type)