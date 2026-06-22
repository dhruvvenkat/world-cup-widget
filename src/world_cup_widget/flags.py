from __future__ import annotations

# Football APIs often return FIFA/IOC three-letter team codes, while flag emoji
# are generated from ISO 3166-1 alpha-2 country codes. This map covers current
# and common World Cup teams, plus a few API-specific variants.
FIFA_TO_ISO2: dict[str, str] = {
    "ARG": "AR",
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "BRA": "BR",
    "CAN": "CA",
    "CHI": "CL",
    "CHN": "CN",
    "CMR": "CM",
    "COL": "CO",
    "CRC": "CR",
    "CRO": "HR",
    "DEN": "DK",
    "ECU": "EC",
    "EGY": "EG",
    "ENG": "GB-ENG",
    "ESP": "ES",
    "FRA": "FR",
    "GER": "DE",
    "GHA": "GH",
    "GRE": "GR",
    "IRN": "IR",
    "ITA": "IT",
    "JPN": "JP",
    "KOR": "KR",
    "MAR": "MA",
    "MEX": "MX",
    "NED": "NL",
    "NGA": "NG",
    "NOR": "NO",
    "NZL": "NZ",
    "PAN": "PA",
    "PAR": "PY",
    "PER": "PE",
    "POL": "PL",
    "POR": "PT",
    "QAT": "QA",
    "ROU": "RO",
    "KSA": "SA",
    "SCO": "GB-SCT",
    "SEN": "SN",
    "SRB": "RS",
    "SUI": "CH",
    "SWE": "SE",
    "TUN": "TN",
    "TUR": "TR",
    "UKR": "UA",
    "URU": "UY",
    "USA": "US",
    "WAL": "GB-WLS",
}

SUBDIVISION_FLAGS = {
    "GB-ENG": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "GB-SCT": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    "GB-WLS": "🏴\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
}


def flag_for_code(code: str | None) -> str:
    if not code:
        return ""
    normalized = code.strip().upper()
    iso2 = FIFA_TO_ISO2.get(normalized, normalized if len(normalized) == 2 else "")
    if not iso2:
        return ""
    if iso2 in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[iso2]
    if len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(ord(char) - ord("A") + 0x1F1E6) for char in iso2)
