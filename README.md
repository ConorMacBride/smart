# `smart`
An opinionated smart home API that extends tadoº smart thermostat scheduling abilities.

## Installation
Clone the `smart` repository:
```
git clone https://github.com/ConorMacBride/smart.git
```

Checkout the [latest tag](https://github.com/ConorMacBride/smart/releases), e.g.:
```
git checkout v1.0.0
```

Create a virtual Python environment, and then install the package:
```
pip install -e .
```

Create a `data` directory somewhere.
Inside it create a `schedules` directory to contain various custom schedules, e.g., `/data/schedules/winter.toml`:

```toml
[metadata]
name = "Winter Schedule" # Display name for selecting the schedule

[[kitchen]] # A set command for the "Kitchen" zone
time = "00:00" # Turn off kitchen zone at midnight
temperature = 0

[[kitchen]]
time = "06:00" # Set kitchen zone to 18ºC at 6 AM
temperature = 18

[[kitchen]]
time = "18:00"
temperature = 19

[[dining_room]] # A set command for the "Dining Room" zone
time = "14:00"
temperature = 17.5

[[dining_room]]
time = "17:00"
temperature = 19

[[dining_room]]
time = "21:00"
temperature = 0
```

You must define a schedule for all the zones in your tadoº system.
All your zones must be set to use a "one day" schedule that applies Monday to Sunday.

More complex dynamic schedules can also be created:

```toml
[metadata]
name = "Dynamic Schedule"
sleep = "00:00" # Default value for the `sleep` variable time
wake = "08:00"

[[variant]] # A duplicate of this schedule but with different default values
name = "Up at 9 AM"
wake = "09:00"

[[variant]]
name = "Bed at 2 AM"
sleep = "02:00"

[[kitchen]]
time = "{sleep|+01:00}" # One hour after the value of the `sleep` variable
temperature = 0

[[kitchen]]
time = "{wake}" # The value of the `wake` variable
temperature = 18

[[kitchen]]
time = "18:00"
temperature = 19

[[dining_room]]
time = "14:00"
temperature = 17.5

[[dining_room]]
time = "17:00"
temperature = 19

[[dining_room]]
time = "{sleep|-04:00}" # Four hours before the value of the `sleep` variable
temperature = 0
```

Create a `.env` file at the root of this repository, e.g.:
```
API_KEY=<generate your own api key for accessing your endpoints>
TADO_USERNAME=yourname@example.com
TADO_PASSWORD=YourTadoPassword
TADO_DATA=/path/to/data
TADO_DEFAULT_SCHEDULE="Winter Schedule"
```

There is also an optional `TADO_ENV` that has a default value of `https://my.tado.com/webapp/env.js`.

```
uvicorn app.main:app
```

To make the API accessible outside the machine you are hosting it on, read the uvicorn documentation and elsewhere on how to specify the host and port.
You must also consider hardening the security of your deployment (e.g., SSL keys, firewall rules, ...) to protect your endpoint, server and other devices within your home network.

You may wish to look into running the server as a system service.

## Usage

Various API endpoints are included.
You can interact with them by creating some Apple Shortcuts, for example.

### `/tado/schedule/all`: List all configured schedules
```
curl \
  -H "x-api-key: yourAPIkey" \
  http://127.0.0.1:8000/tado/schedule/all
```

### `/tado/schedule/set`: Activate one your configured schedules
```
curl \
  -H "x-api-key: yourAPIkey" \
  -H "Content-Type: application/json" \
  --request POST \
  --data '{"name": "Dynamic Schedule", "variables": {"wake": "07:00", "sleep": "23:00"}}' \
  http://127.0.0.1:8000/tado/schedule/set
```

### `/tado/schedule/active`: Show the current active schedule
```
curl \
  -H "x-api-key: yourAPIkey" \
  http://127.0.0.1:8000/tado/schedule/active
```

### `/tado/schedule/reset`: Activate `TADO_DEFAULT_SCHEDULE`
```
curl \
  -H "x-api-key: yourAPIkey" \
  http://127.0.0.1:8000/tado/schedule/reset
```

### `/tado/away`: Set tadoº to AWAY mode
```
curl \
  -H "x-api-key: yourAPIkey" \
  http://127.0.0.1:8000/tado/away
```

### `/tado/home`: Set tadoº to HOME mode
```
curl \
  -H "x-api-key: yourAPIkey" \
  http://127.0.0.1:8000/tado/home
```
