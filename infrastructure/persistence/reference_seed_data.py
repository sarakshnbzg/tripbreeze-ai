"""Seed datasets for DB-backed reference tables.

These are bootstrap values, not the primary runtime source of truth.
The app seeds them into Postgres and falls back to them only when needed.
"""

AIRLINES = [
    "Delta", "United", "American", "Southwest", "JetBlue", "Alaska", "Spirit",
    "Frontier", "Hawaiian", "British Airways", "Lufthansa", "Air France", "KLM",
    "Iberia", "Swiss", "Austrian", "SAS", "Finnair", "TAP Portugal",
    "Turkish Airlines", "Emirates", "Qatar Airways", "Etihad", "Saudia",
    "Singapore Airlines", "Cathay Pacific", "ANA", "JAL", "Korean Air",
    "Asiana", "Thai Airways", "Air India", "Qantas", "Air New Zealand",
    "LATAM", "Avianca", "Air Canada", "WestJet",
    "Ryanair", "EasyJet", "Vueling", "Norwegian",
]

CITY_TO_AIRPORT: dict[str, str] = {
    "Atlanta": "ATL", "Los Angeles": "LAX", "Chicago": "ORD", "Dallas": "DFW",
    "Denver": "DEN", "New York": "JFK", "San Francisco": "SFO", "Seattle": "SEA",
    "Las Vegas": "LAS", "Orlando": "MCO", "Miami": "MIA", "Charlotte": "CLT",
    "Phoenix": "PHX", "Houston": "IAH", "Boston": "BOS", "Minneapolis": "MSP",
    "Detroit": "DTW", "Philadelphia": "PHL", "Washington D.C.": "DCA",
    "Austin": "AUS", "Honolulu": "HNL", "San Diego": "SAN", "Tampa": "TPA",
    "Toronto": "YYZ", "Vancouver": "YVR", "Montreal": "YUL",
    "Mexico City": "MEX", "Cancun": "CUN", "Havana": "HAV",
    "London": "LHR", "Paris": "CDG", "Frankfurt": "FRA", "Amsterdam": "AMS",
    "Madrid": "MAD", "Barcelona": "BCN", "Rome": "FCO", "Munich": "MUC",
    "Zurich": "ZRH", "Istanbul": "IST", "Lisbon": "LIS", "Berlin": "BER",
    "Vienna": "VIE", "Prague": "PRG", "Athens": "ATH", "Budapest": "BUD",
    "Copenhagen": "CPH", "Dublin": "DUB", "Edinburgh": "EDI", "Florence": "FLR",
    "Reykjavik": "KEF", "Santorini": "JTR",
    "Dubai": "DXB", "Doha": "DOH",
    "Singapore": "SIN", "Tokyo": "NRT", "Seoul": "ICN", "Hong Kong": "HKG",
    "Bangkok": "BKK", "Delhi": "DEL", "Mumbai": "BOM", "Bali": "DPS",
    "Kyoto": "KIX", "Osaka": "KIX", "Phuket": "HKT",
    "Sydney": "SYD", "Melbourne": "MEL", "Auckland": "AKL",
    "Sao Paulo": "GRU", "Bogota": "BOG", "Lima": "LIM", "Santiago": "SCL",
    "Buenos Aires": "EZE", "Rio de Janeiro": "GIG",
    "Cape Town": "CPT", "Johannesburg": "JNB", "Cairo": "CAI",
    "Nairobi": "NBO", "Marrakech": "RAK", "Maldives": "MLE",
}

DAILY_EXPENSE_BY_DESTINATION: dict[str, float] = {
    "amsterdam": 135.0,
    "athens": 80.0,
    "bali": 45.0,
    "bangkok": 55.0,
    "barcelona": 100.0,
    "berlin": 95.0,
    "budapest": 80.0,
    "copenhagen": 175.0,
    "dubai": 165.0,
    "dubrovnik": 115.0,
    "edinburgh": 130.0,
    "hong kong": 110.0,
    "istanbul": 35.0,
    "lisbon": 85.0,
    "london": 165.0,
    "new york": 180.0,
    "paris": 110.0,
    "prague": 80.0,
    "reykjavik": 210.0,
    "rome": 105.0,
    "seoul": 85.0,
    "singapore": 150.0,
    "sydney": 130.0,
    "tokyo": 95.0,
    "vienna": 120.0,
}
