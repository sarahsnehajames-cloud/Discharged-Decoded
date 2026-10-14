import requests
from urllib.parse import quote


def find_pharmacies(location):
    """Find nearby pharmacies using OpenStreetMap data."""
    headers = {
        "User-Agent": "DischargedDecoded/1.0"
    }

    try:
        # Convert the postcode or town into coordinates.
        geo_response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location,
                "format": "jsonv2",
                "countrycodes": "gb",
                "limit": 1,
            },
            headers=headers,
            timeout=15,
        )
        geo_response.raise_for_status()
        places = geo_response.json()

        if not places:
            return []

        latitude = float(places[0]["lat"])
        longitude = float(places[0]["lon"])

        # Search for pharmacies within 5 km.
        query = f"""
        [out:json][timeout:20];
        nwr(around:5000,{latitude},{longitude})
          ["amenity"="pharmacy"];
        out center tags;
        """

        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        pharmacies = []

        for place in response.json().get("elements", []):
            tags = place.get("tags", {})

            lat = place.get("lat")
            lon = place.get("lon")

            if place["type"] == "way" or place["type"] == "relation":
                center = place.get("center", {})
                lat = center.get("lat")
                lon = center.get("lon")

            if lat is None or lon is None:
                continue

            name = tags.get("name", "Unnamed pharmacy")
            address = ", ".join(
                part for part in [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:city"),
                    tags.get("addr:postcode"),
                ]
                if part
            )

            directions = (
                "https://www.google.com/maps/dir/?api=1"
                f"&destination={quote(str(lat) + ',' + str(lon))}"
            )

            pharmacies.append({
                "name": name,
                "address": address or "Address not listed",
                "directions": directions,
                "latitude": lat,
                "longitude": lon,
            })

        return pharmacies

    except requests.RequestException:
        return None
