# Apple Predictor Bot

Apple Predictor Bot is a Telegram bot designed to simulate the Apple of Fortune game on 1xbet. It provides predictions, tracks user history, and offers features like exporting/importing data, viewing statistics, and more.

## Features

- **Prediction Simulation**: Simulates predictions for 1xbet's Apple of Fortune game using RNG.
- **User History Tracking**: Tracks user predictions and results in a SQLite database.
- **Statistics**: Displays user-specific statistics, including win rates for different odds.
- **Export/Import**: Allows users to export their history in JSON, CSV, or TXT formats and import data back into the bot.
- **Access Control**: Implements access control with unique codes for restricted features.
- **Admin Features**: Admins can generate access codes and manage users.
- **Educational Content**: Provides tips, FAQs, and warnings about scams.

## Setup

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (obtainable from [BotFather](https://core.telegram.org/bots#botfather))
- SQLite (comes pre-installed with Python)

### Installation

1. Clone the repository or copy the script to your local machine.
2. Install the required Python libraries:
   ```bash
   pip install python-telegram-bot
   ```
3. Replace the placeholder `YOUR_TELEGRAM_ID` in the script with your Telegram user ID for admin access.
4. Replace the `TOKEN` variable with your bot's token.

### Database Initialization

The bot automatically initializes the SQLite database (`apple_predictor.db`) when it starts. It creates the following tables:
- `users`: Stores user information.
- `history`: Tracks user predictions and results.
- `access_control`: Manages access codes and expiration times.

## Usage

### Starting the Bot

Run the bot using:
```bash
python tera\ 1.py
```

### Commands

#### General Commands
- `/start`: Start the bot and display the main menu.
- `/fonctionnement`: Explain how the game works.
- `/conseils`: Provide responsible gaming tips.
- `/arnaques`: Warn about scams.
- `/contact`: Display contact information.
- `/faq`: Answer frequently asked questions.
- `/tuto`: Provide a quick tutorial.
- `/apropos`: Display information about the bot.
- `/historique`: Show the user's history.
- `/statistiques` or `/stats`: Display user-specific statistics.

#### Admin Commands
- `/generate_code <user_id> <duration_in_minutes>`: Generate an access code for a user.
- `/admin`: Access the admin menu.

#### Protected Commands
- `/protected`: Example of a command protected by access control.

#### Export/Import
- `/import`: Prompt the user to upload a file (JSON, CSV, or TXT) for importing history.
- Export options are available via the "📤 Exporter" button in the menu.

### Menu Buttons

The bot provides a rich menu with buttons for easy navigation:
- **Prediction**: Start a prediction sequence.
- **Export/Import**: Export or import user history.
- **Reset History**: Clear the user's history.
- **Educational Content**: Access tips, FAQs, and scam warnings.

### Access Control

Certain features are restricted and require an access code. Admins can generate codes using the `/generate_code` command.

## File Structure

- `tera 1.py`: Main bot script.
- `apple_predictor.db`: SQLite database (auto-created).

## Contributing

Feel free to fork the repository and submit pull requests for improvements or new features.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Contact

For questions or support, contact:
- WhatsApp: [wa.me/+2250501945735](https://wa.me/+2250501945735)
- Telegram: [@Roidesombres225](https://t.me/Roidesombres225)
