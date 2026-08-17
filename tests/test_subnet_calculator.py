"""
Tests unitaires pour subnet_calculator.py

Lancer avec : pytest
"""

import ipaddress
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subnet_calculator import mask_to_binary, get_address_type, get_usable_hosts


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
