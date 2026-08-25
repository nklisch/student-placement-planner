# Online routing setup

Google Maps is optional. The **Community OpenStreetMap services** option needs no account or key and is suitable for occasional use. A free [openrouteservice](https://openrouteservice.org/dev/#/signup) account is another alternative. Manual travel times and downloaded offline regions need no online routing service at all.

The community option uses the public Nominatim address service at its required one-request-per-second rate, then sends reviewed coordinates to the public OSRM router. These shared services can be busy or unavailable and have no service guarantee. Existing times are always retained if a request fails.

openrouteservice and Google keys are kept only in memory until the app closes. They are not written into projects, exports, troubleshooting details, or logs.

## What is sent

When you choose Google Maps, Student Placement Planner sends only the street addresses or coordinates needed to find routes. Student names, IDs, choices, capacities, and rules are never included in Google requests.

The same privacy boundary applies to the community and openrouteservice options. Each selected provider receives addresses or coordinates, but never roster names, IDs, choices, capacities, or placement rules.

## Create a Google key

1. Open the [Google Maps Platform setup guide](https://developers.google.com/maps/documentation/routes/cloud-setup).
2. Create or select a Google Cloud project and enable billing.
3. Enable both **Geocoding API** and **Routes API**.
4. Create an API key.
5. Restrict that key to the Geocoding API and Routes API, and set quotas that fit your expected use.
6. Paste the key into **Travel times → Online route services → Google Maps API key** and select **Test connection**.

Google charges the owner of the Cloud project according to its current pricing and quotas. Student Placement Planner does not add a fee or send requests in the background.

## Create an openrouteservice key

1. Create a free account on the [openrouteservice developer portal](https://openrouteservice.org/dev/#/signup).
2. Create an API key for the standard service.
3. Paste it into **Travel times → Online route services → openrouteservice API key**.
4. Select **Test connection**.

The provider's free-plan request limits apply. The app splits larger tables into smaller requests and reports when the allowance has been reached.

## Calculate times

Select **Review addresses and calculate**. The app first shows every address match without sending student names. Correct any latitude/longitude that is wrong, then approve the list. Route calculation runs away from the interface and can be cancelled safely.

Existing travel times are kept if Google is unavailable, a quota is reached, or the operation is cancelled.

## Common messages

- **Check the API key, enabled APIs, and billing:** confirm that both APIs are enabled in the same Cloud project as the key.
- **Quota was reached:** wait for the quota window to reset or adjust the project quota.
- **Address was not found:** correct the address in Students or Locations, or enter coordinates directly.
- **Could not be reached:** check the internet connection and try again, use an offline region, or enter times manually.
