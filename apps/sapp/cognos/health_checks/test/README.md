Perform Smoke Testing

After starting all services, navigate to the smoke test folder:
   cd sapp/cognos/health_checks/test folder

Run the smoke test script:
   chmod +x ./smoke_test.sh
  ./smoke_test.sh

The script will check:
1. If the backend service is running.
2. If the database is accessible.
3. If the frontend is functioning as expected.

Additional Information
1. If any service is down or fails, the script will output the relevant failure messages.
2. Ensure you have appropriate permissions to run the script.