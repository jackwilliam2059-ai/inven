"""
SQLAlchemy 모델 정의 - Supabase PostgreSQL 연동
재고관리 프로그램 기준 완전한 스키마
"""
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date, 
    ForeignKey, ARRAY, Numeric, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Organization(Base):
    """조직 (멀티테넌시)"""
    __tablename__ = 'organizations'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    products = relationship("Product", back_populates="organization", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="organization", cascade="all, delete-orphan")
    stores = relationship("Store", back_populates="organization", cascade="all, delete-orphan")
    inbound_records = relationship("InboundRecord", back_populates="organization", cascade="all, delete-orphan")
    outbound_records = relationship("OutboundRecord", back_populates="organization", cascade="all, delete-orphan")
    inventory_movements = relationship("InventoryMovement", back_populates="organization", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="organization", cascade="all, delete-orphan")
    settlement_balances = relationship("SettlementBalance", back_populates="organization", cascade="all, delete-orphan")


class Store(Base):
    """매장"""
    __tablename__ = 'stores'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text)
    phone = Column(String(50))
    is_warehouse = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="stores")
    orders = relationship("Order", back_populates="store")
    outbound_records = relationship("OutboundRecord", back_populates="store")
    
    __table_args__ = (
        Index('idx_stores_org', 'organization_id'),
    )


class Tag(Base):
    """태그 (상품 분류용)"""
    __tablename__ = 'tags'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    color = Column(String(20), default='#2196F3')
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="tags")
    product_tags = relationship("ProductTag", back_populates="tag", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'name', name='uq_tag_org_name'),
        Index('idx_tags_org', 'organization_id'),
    )


class Product(Base):
    """상품"""
    __tablename__ = 'products'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(100))
    supplier = Column(String(255))
    colors = Column(ARRAY(String), default=[])
    sizes = Column(ARRAY(String), default=[])
    memo = Column(Text)
    order_unit = Column(Integer)
    image_url = Column(Text)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="products")
    orders = relationship("Order", back_populates="product")
    inbound_records = relationship("InboundRecord", back_populates="product")
    outbound_records = relationship("OutboundRecord", back_populates="product")
    inventory_movements = relationship("InventoryMovement", back_populates="product")
    product_tags = relationship("ProductTag", back_populates="product", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_products_org', 'organization_id'),
        Index('idx_products_name', 'organization_id', 'name'),
        Index('idx_products_code', 'organization_id', 'code'),
        Index('idx_products_active', 'organization_id', 'is_active'),
        Index('idx_products_sort', 'organization_id', 'sort_order'),
    )
    
    @property
    def tag_names(self):
        """태그 이름 목록"""
        return [pt.tag.name for pt in self.product_tags if pt.tag]


class ProductTag(Base):
    """상품-태그 연결 테이블"""
    __tablename__ = 'product_tags'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_id = Column(BigInteger, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    tag_id = Column(BigInteger, ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="product_tags")
    tag = relationship("Tag", back_populates="product_tags")
    
    __table_args__ = (
        UniqueConstraint('product_id', 'tag_id', name='uq_product_tag'),
        Index('idx_product_tags_product', 'product_id'),
        Index('idx_product_tags_tag', 'tag_id'),
    )


class Order(Base):
    """발주"""
    __tablename__ = 'orders'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    store_id = Column(BigInteger, ForeignKey('stores.id', ondelete='SET NULL'))
    order_date = Column(Date, nullable=False)
    color = Column(String(100))
    size = Column(String(50), default='FREE')
    quantity = Column(Integer, nullable=False)
    shipped_quantity = Column(Integer, default=0)
    status = Column(String(50), default='pending')
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="orders")
    product = relationship("Product", back_populates="orders")
    store = relationship("Store", back_populates="orders")
    
    __table_args__ = (
        Index('idx_orders_org_date', 'organization_id', 'order_date'),
        Index('idx_orders_product', 'organization_id', 'product_id'),
        Index('idx_orders_status', 'organization_id', 'status'),
        CheckConstraint('quantity > 0', name='check_order_quantity_positive'),
    )
    
    @property
    def pending_quantity(self):
        """미입고 수량"""
        return self.quantity - (self.shipped_quantity or 0)


class InboundRecord(Base):
    """입고 기록"""
    __tablename__ = 'inbound_records'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    color = Column(String(100))
    size = Column(String(50), default='FREE')
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="inbound_records")
    product = relationship("Product", back_populates="inbound_records")
    
    __table_args__ = (
        Index('idx_inbound_org_date', 'organization_id', 'date'),
        Index('idx_inbound_product', 'organization_id', 'product_id'),
    )


class OutboundRecord(Base):
    """출고 기록"""
    __tablename__ = 'outbound_records'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    store_id = Column(BigInteger, ForeignKey('stores.id', ondelete='SET NULL'))
    date = Column(Date, nullable=False)
    color = Column(String(100))
    size = Column(String(50), default='FREE')
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="outbound_records")
    product = relationship("Product", back_populates="outbound_records")
    store = relationship("Store", back_populates="outbound_records")
    
    __table_args__ = (
        Index('idx_outbound_org_date', 'organization_id', 'date'),
        Index('idx_outbound_product', 'organization_id', 'product_id'),
        Index('idx_outbound_store', 'organization_id', 'store_id'),
    )


class InventoryMovement(Base):
    """재고 이동 (창고 ↔ 매장 / 매장 ↔ 매장)"""
    __tablename__ = 'inventory_movements'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(BigInteger, ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    color = Column(String(100))
    size = Column(String(50), default='FREE')
    quantity = Column(Integer, nullable=False)
    from_location = Column(String(255))
    to_location = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="inventory_movements")
    product = relationship("Product", back_populates="inventory_movements")
    
    __table_args__ = (
        Index('idx_movements_org_date', 'organization_id', 'date'),
        Index('idx_movements_product', 'organization_id', 'product_id'),
    )


class FieldName(Base):
    """커스텀 필드명"""
    __tablename__ = 'field_names'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    field_index = Column(Integer, nullable=False)
    field_name = Column(String(100), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'field_index', name='uq_field_org_index'),
    )


class SettlementBalance(Base):
    """정산 잔액"""
    __tablename__ = 'settlement_balances'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    supplier = Column(String(255), nullable=False)
    balance = Column(Numeric(15, 2), default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="settlement_balances")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'supplier', name='uq_settlement_org_supplier'),
        Index('idx_settlement_org', 'organization_id'),
    )
