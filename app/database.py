"""SQLite 데이터베이스 설정 - Redis와 비교 실습용"""

import os

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/app.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    price = Column(Integer, nullable=False)
    stock = Column(Integer, default=0)
    description = Column(Text, default="")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False, unique=True)
    score = Column(Integer, default=0)


async def init_db():
    """테이블 생성 및 샘플 데이터 삽입"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # 이미 데이터가 있으면 스킵
        from sqlalchemy import select, func

        result = await session.execute(select(func.count()).select_from(Product))
        if result.scalar() > 0:
            return

        products = [
            Product(id=1, name="무선 키보드", price=59000, stock=120, description="블루투스 5.0 키보드"),
            Product(id=2, name="기계식 마우스", price=35000, stock=85, description="RGB 게이밍 마우스"),
            Product(id=3, name="27인치 모니터", price=350000, stock=30, description="4K UHD 모니터"),
            Product(id=4, name="USB-C 허브", price=45000, stock=200, description="7-in-1 허브"),
            Product(id=5, name="노트북 스탠드", price=28000, stock=150, description="알루미늄 스탠드"),
        ]
        posts = [
            Post(id=1, title="Redis 입문 가이드", content="Redis는 인메모리 데이터 구조 서버입니다.", views=0, likes=0),
            Post(id=2, title="FastAPI 시작하기", content="Python 비동기 웹 프레임워크입니다.", views=0, likes=0),
            Post(id=3, title="Docker 기초", content="컨테이너 기반 가상화 플랫폼입니다.", views=0, likes=0),
        ]
        users = [
            User(id=1, name="Alice", email="alice@example.com", score=2500),
            User(id=2, name="Bob", email="bob@example.com", score=3200),
            User(id=3, name="Charlie", email="charlie@example.com", score=4100),
            User(id=4, name="Diana", email="diana@example.com", score=4800),
            User(id=5, name="Eve", email="eve@example.com", score=5500),
        ]
        session.add_all(products + posts + users)
        await session.commit()
