import asyncio, os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        # order matters: children before parents, because of the pointers
        await conn.execute(text("DELETE FROM answers"))
        await conn.execute(text("DELETE FROM images"))
        await conn.execute(text("DELETE FROM questions"))
        await conn.execute(text("DELETE FROM papers"))
    await engine.dispose()
    
    print("rows cleared")

asyncio.run(main())