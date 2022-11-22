from typing import Dict, Any

from nomenklatura.dataset import DataCatalog


def test_catalog_base(catalog_data: Dict[str, Any]):
    catalog = DataCatalog.from_dict(catalog_data)
    assert len(catalog.datasets) == 3, catalog.datasets
    ds = catalog.get("donations")
    assert ds is not None, ds
    assert ds.name == "donations"
