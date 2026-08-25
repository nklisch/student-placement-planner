# Google Maps setup

Google Maps is optional. Manual travel times and downloaded offline regions work without a Google account or API key.

## What is sent

When you choose Google Maps, Student Placement Planner sends only the street addresses or coordinates needed to find routes. Student names, IDs, choices, capacities, and rules are never included in Google requests.

The API key is kept in memory until the app closes. It is not written into project files, exports, troubleshooting details, or logs.

## Create a key

1. Open the [Google Maps Platform setup guide](https://developers.google.com/maps/documentation/routes/cloud-setup).
2. Create or select a Google Cloud project and enable billing.
3. Enable both **Geocoding API** and **Routes API**.
4. Create an API key.
5. Restrict that key to the Geocoding API and Routes API, and set quotas that fit your expected use.
6. Paste the key into **Travel times → Online maps (Google)** and select **Test connection**.

Google charges the owner of the Cloud project according to its current pricing and quotas. Student Placement Planner does not add a fee or send requests in the background.

## Calculate times

Select **Review addresses and calculate**. The app first shows every address match without sending student names. Correct any latitude/longitude that is wrong, then approve the list. Route calculation runs away from the interface and can be cancelled safely.

Existing travel times are kept if Google is unavailable, a quota is reached, or the operation is cancelled.

## Common messages

- **Check the API key, enabled APIs, and billing:** confirm that both APIs are enabled in the same Cloud project as the key.
- **Quota was reached:** wait for the quota window to reset or adjust the project quota.
- **Address was not found:** correct the address in Students or Locations, or enter coordinates directly.
- **Could not be reached:** check the internet connection and try again, use an offline region, or enter times manually.
