"""Abstract connector interfaces. Real ERP/WMS/OMS integrations implement these;
the sandbox uses the mock_* implementations as the deterministic source of truth
that business validators also read from."""
from abc import ABC, abstractmethod


class ERPConnector(ABC):
    @abstractmethod
    def get_inventory_snapshot(self) -> list[dict]: ...

    @abstractmethod
    def get_suppliers(self) -> list[dict]: ...

    @abstractmethod
    def get_demand_history(self) -> list[dict]: ...

    @abstractmethod
    def create_purchase_order(self, supplier_id: str, sku: str, quantity: int) -> dict: ...


class WMSConnector(ABC):
    @abstractmethod
    def get_warehouses(self) -> list[dict]: ...

    @abstractmethod
    def get_storage_constraints(self, warehouse_id: str) -> dict: ...
