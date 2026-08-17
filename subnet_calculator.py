#!/usr/bin/env python3
"""
Calculateur de Sous-Réseaux IP (IPv4 & IPv6)
=============================================

Outil en ligne de commande qui calcule et affiche les informations
essentielles d'un réseau à partir d'une adresse IP saisie au format CIDR
(ex: 192.168.1.45/24 ou 2001:db8::/32).

Auteur : à personnaliser
Licence : MIT
"""

import ipaddress
import sys

# Sur Windows, la console utilise par défaut un encodage (cp1252) qui ne
# gère pas bien les caractères accentués. On force l'UTF-8 pour un affichage
# correct des textes en français.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


# --------------------------------------------------------------------------- #
# Fonctions de calcul réseau
# --------------------------------------------------------------------------- #

def mask_to_binary(network: ipaddress.IPv4Network | ipaddress.IPv6Network) -> str:
    """
    Convertit le masque de sous-réseau en une représentation binaire lisible.

    Pour IPv4, le résultat est découpé en 4 groupes de 8 bits (ex: 11111111.11111111.11111111.00000000).
    Pour IPv6, le résultat est découpé en groupes de 16 bits pour rester lisible.
    """
    netmask_int = int(network.netmask)

    if network.version == 4:
        bits = format(netmask_int, "032b")
        return ".".join(bits[i:i + 8] for i in range(0, 32, 8))
    else:
        bits = format(netmask_int, "0128b")
        return ":".join(bits[i:i + 16] for i in range(0, 128, 16))


def get_address_type(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """
    Détermine le type de l'adresse IP : Loopback, Privée ou Publique.

    On teste d'abord les cas particuliers (loopback, lien-local, multicast, etc.)
    car ils sont "is_private" == True mais méritent un libellé plus précis.
    """
    if ip.is_loopback:
        return "Loopback"
    if ip.is_link_local:
        return "Lien-local (APIPA / IPv6 link-local)"
    if ip.is_multicast:
        return "Multicast"
    if ip.is_reserved:
        return "Réservée"
    if ip.is_unspecified:
        return "Non spécifiée"
    if ip.is_private:
        return "Privée"
    return "Publique"


def get_usable_hosts(network: ipaddress.IPv4Network | ipaddress.IPv6Network):
    """
    Calcule la première et la dernière adresse IP attribuable (utilisable) du réseau,
    ainsi que le nombre total d'hôtes disponibles.

    Règles IPv4 :
      - Un réseau /31 ou /32 n'a pas d'adresse réseau/broadcast "classique"
        (RFC 3021 pour les liaisons point-à-point). On gère ce cas séparément.
      - Sinon, la plage utilisable exclut l'adresse réseau et l'adresse de broadcast.

    Règles IPv6 :
      - Il n'y a pas de notion de broadcast en IPv6. Toutes les adresses de la
        plage sont potentiellement utilisables, hormis l'adresse réseau elle-même
        (adresse "tous zéros"), par convention.
    """
    if network.version == 4:
        if network.prefixlen >= 31:
            # /31 (2 adresses, point-à-point) ou /32 (hôte unique)
            hosts = list(network.hosts())
            if not hosts:
                # /32 : une seule adresse, elle est à la fois réseau et hôte
                first_usable = last_usable = network.network_address
                total_hosts = 1
            else:
                first_usable, last_usable = hosts[0], hosts[-1]
                total_hosts = len(hosts)
        else:
            first_usable = network.network_address + 1
            last_usable = network.broadcast_address - 1
            total_hosts = network.num_addresses - 2
    else:
        # IPv6 : pas de broadcast, on exclut uniquement l'adresse réseau
        total_hosts = network.num_addresses - 1
        first_usable = network.network_address + 1 if network.num_addresses > 1 else network.network_address
        last_usable = network[-1]

    return first_usable, last_usable, total_hosts


# --------------------------------------------------------------------------- #
# Affichage (rich)
# --------------------------------------------------------------------------- #

def display_results(network: ipaddress.IPv4Network | ipaddress.IPv6Network, ip_input: str) -> None:
    """Construit et affiche un tableau récapitulatif des informations du réseau."""

    version_label = "IPv4" if network.version == 4 else "IPv6"
    host_ip = ipaddress.ip_interface(ip_input).ip

    first_usable, last_usable, total_hosts = get_usable_hosts(network)

    table = Table(
        title=f"Résultats du calcul — {version_label}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("Propriété", style="bold white", no_wrap=True)
    table.add_column("Valeur", style="green")

    table.add_row("Adresse saisie", ip_input)
    table.add_row("Version", version_label)
    table.add_row("Adresse réseau", str(network.network_address))
    table.add_row("Préfixe CIDR", f"/{network.prefixlen}")

    if network.version == 4:
        table.add_row("Masque (décimal)", str(network.netmask))
        table.add_row("Masque (binaire)", mask_to_binary(network))
        table.add_row("Adresse de broadcast", str(network.broadcast_address))
    else:
        table.add_row("Masque (binaire)", mask_to_binary(network))

    table.add_row("Première IP utilisable", str(first_usable))
    table.add_row("Dernière IP utilisable", str(last_usable))
    table.add_row("Nombre total d'hôtes", f"{total_hosts:,}".replace(",", " "))
    table.add_row("Type de l'adresse saisie", get_address_type(host_ip))

    console.print(table)


def display_error(message: str) -> None:
    """Affiche un message d'erreur dans un cadre rouge, clair et lisible."""
    console.print(Panel(f"[bold red]Erreur :[/bold red] {message}", border_style="red", title="Entrée invalide"))


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def calculate_subnet(ip_input: str) -> None:
    """
    Point d'entrée du calcul : valide l'entrée utilisateur, construit l'objet
    réseau (ipaddress) et déclenche l'affichage des résultats.

    `strict=False` permet d'accepter une adresse d'hôte (ex: 192.168.1.45/24)
    sans lever d'exception, contrairement au mode strict qui exige une adresse
    réseau exacte (ex: 192.168.1.0/24).
    """
    try:
        interface = ipaddress.ip_interface(ip_input)
        network = interface.network
    except ValueError:
        display_error(
            "Le format saisi n'est pas une adresse IP/CIDR valide.\n"
            "Exemples attendus : 192.168.1.45/24  ou  2001:db8::/32"
        )
        return

    display_results(network, ip_input)


def print_banner() -> None:
    """Affiche le titre d'accueil de l'application."""
    console.print(
        Panel(
            "[bold cyan]Calculateur de Sous-Réseaux IP[/bold cyan]\n"
            "[white]Compatible IPv4 & IPv6 — propulsé par le module Python `ipaddress`[/white]",
            border_style="cyan",
            box=box.DOUBLE,
        )
    )


def main() -> None:
    """
    Boucle principale du programme.

    Deux modes d'utilisation :
      1. En argument de ligne de commande : python subnet_calculator.py 192.168.1.45/24
      2. En mode interactif : python subnet_calculator.py (puis saisie manuelle)
    """
    print_banner()

    if len(sys.argv) > 1:
        calculate_subnet(sys.argv[1])
        return

    console.print("[bold]Entrez une adresse IP au format CIDR[/bold] (ex: [italic]192.168.1.45/24[/italic]).")
    console.print("[dim]Tapez 'quit' ou 'exit' pour quitter.[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]➜ Adresse IP/CIDR : [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Au revoir ![/dim]")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Au revoir ![/dim]")
            break

        if not user_input:
            continue

        calculate_subnet(user_input)
        console.print()  # ligne vide pour aérer l'affichage


if __name__ == "__main__":
    main()
