"""
Tests unitaires pour subnet_calculator.py

Lancer avec : pytest
"""

import csv
import ipaddress
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subnet_calculator import (
    mask_to_binary,
    get_address_type,
    get_usable_hosts,
    build_result_dict,
    split_network,
    supernet_networks,
    export_results_csv,
    export_results_json,
)


# --------------------------------------------------------------------------- #
# mask_to_binary
# --------------------------------------------------------------------------- #

def test_mask_to_binary_ipv4_24():
    network = ipaddress.ip_network("192.168.1.0/24")
    assert mask_to_binary(network) == "11111111.11111111.11111111.00000000"


def test_mask_to_binary_ipv4_8():
    network = ipaddress.ip_network("10.0.0.0/8")
    assert mask_to_binary(network) == "11111111.00000000.00000000.00000000"


def test_mask_to_binary_ipv6_32():
    network = ipaddress.ip_network("2001:db8::/32")
    binary = mask_to_binary(network)
    assert binary.startswith("1111111111111111:1111111111111111:0000000000000000")


# --------------------------------------------------------------------------- #
# get_address_type
# --------------------------------------------------------------------------- #

def test_get_address_type_private():
    assert get_address_type(ipaddress.ip_address("192.168.1.45")) == "Privée"


def test_get_address_type_public():
    assert get_address_type(ipaddress.ip_address("8.8.8.8")) == "Publique"


def test_get_address_type_loopback():
    assert get_address_type(ipaddress.ip_address("127.0.0.1")) == "Loopback"


def test_get_address_type_link_local():
    assert "Lien-local" in get_address_type(ipaddress.ip_address("169.254.1.1"))


def test_get_address_type_multicast():
    assert get_address_type(ipaddress.ip_address("224.0.0.1")) == "Multicast"


def test_get_address_type_ipv6_loopback():
    assert get_address_type(ipaddress.ip_address("::1")) == "Loopback"


# --------------------------------------------------------------------------- #
# get_usable_hosts
# --------------------------------------------------------------------------- #

def test_get_usable_hosts_ipv4_24():
    network = ipaddress.ip_network("192.168.1.0/24")
    first, last, total = get_usable_hosts(network)
    assert str(first) == "192.168.1.1"
    assert str(last) == "192.168.1.254"
    assert total == 254


def test_get_usable_hosts_ipv4_31_point_to_point():
    network = ipaddress.ip_network("192.168.1.0/31")
    first, last, total = get_usable_hosts(network)
    assert str(first) == "192.168.1.0"
    assert str(last) == "192.168.1.1"
    assert total == 2


def test_get_usable_hosts_ipv4_32_single_host():
    network = ipaddress.ip_network("192.168.1.5/32")
    first, last, total = get_usable_hosts(network)
    assert str(first) == str(last) == "192.168.1.5"
    assert total == 1


def test_get_usable_hosts_ipv6():
    network = ipaddress.ip_network("2001:db8::/126")
    first, last, total = get_usable_hosts(network)
    assert str(first) == "2001:db8::1"
    assert str(last) == "2001:db8::3"
    assert total == 3


# --------------------------------------------------------------------------- #
# build_result_dict
# --------------------------------------------------------------------------- #

def test_build_result_dict_ipv4():
    network = ipaddress.ip_network("192.168.1.0/24")
    result = build_result_dict(network, "192.168.1.45/24")
    assert result["Adresse saisie"] == "192.168.1.45/24"
    assert result["Version"] == "IPv4"
    assert result["Adresse réseau"] == "192.168.1.0"
    assert result["Préfixe CIDR"] == "/24"
    assert result["Nombre total d'hôtes"] == 254
    assert result["Type de l'adresse saisie"] == "Privée"


def test_build_result_dict_ipv6():
    network = ipaddress.ip_network("2001:db8::/32")
    result = build_result_dict(network, "2001:db8::1/32")
    assert result["Version"] == "IPv6"
    assert result["Masque (décimal)"] == "-"
    assert result["Adresse de broadcast"] == "-"


# --------------------------------------------------------------------------- #
# split_network
# --------------------------------------------------------------------------- #

def test_split_network_by_num_subnets():
    network = ipaddress.ip_network("192.168.1.0/24")
    subnets = split_network(network, num_subnets=4)
    assert len(subnets) == 4
    assert all(subnet.prefixlen == 26 for subnet in subnets)
    assert str(subnets[0]) == "192.168.1.0/26"


def test_split_network_by_new_prefix():
    network = ipaddress.ip_network("192.168.1.0/24")
    subnets = split_network(network, new_prefix=26)
    assert len(subnets) == 4


def test_split_network_requires_exactly_one_param():
    network = ipaddress.ip_network("192.168.1.0/24")
    with pytest.raises(ValueError):
        split_network(network)
    with pytest.raises(ValueError):
        split_network(network, num_subnets=2, new_prefix=26)


def test_split_network_invalid_new_prefix_too_small():
    network = ipaddress.ip_network("192.168.1.0/24")
    with pytest.raises(ValueError):
        split_network(network, new_prefix=24)


def test_split_network_invalid_new_prefix_too_large():
    network = ipaddress.ip_network("192.168.1.0/24")
    with pytest.raises(ValueError):
        split_network(network, new_prefix=33)


# --------------------------------------------------------------------------- #
# supernet_networks
# --------------------------------------------------------------------------- #

def test_supernet_networks_aggregates_adjacent():
    result = supernet_networks(["192.168.0.0/25", "192.168.0.128/25"])
    assert len(result) == 1
    assert str(result[0]) == "192.168.0.0/24"


def test_supernet_networks_non_adjacent_stays_separate():
    result = supernet_networks(["10.0.0.0/24", "192.168.0.0/24"])
    assert len(result) == 2


# --------------------------------------------------------------------------- #
# export_results_csv / export_results_json
# --------------------------------------------------------------------------- #

def test_export_results_csv(tmp_path):
    network = ipaddress.ip_network("192.168.1.0/24")
    rows = [build_result_dict(network, "192.168.1.45/24")]
    csv_path = tmp_path / "resultats.csv"
    export_results_csv(rows, csv_path)

    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        read_rows = list(reader)
    assert len(read_rows) == 1
    assert read_rows[0]["Adresse réseau"] == "192.168.1.0"


def test_export_results_json(tmp_path):
    network = ipaddress.ip_network("192.168.1.0/24")
    rows = [build_result_dict(network, "192.168.1.45/24")]
    json_path = tmp_path / "resultats.json"
    export_results_json(rows, json_path)

    with open(json_path, encoding="utf-8") as json_file:
        data = json.load(json_file)
    assert len(data) == 1
    assert data[0]["Adresse réseau"] == "192.168.1.0"
