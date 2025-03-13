# InvoiceTracker

InvoiceTracker is a web application designed to support the debt collection (dunning) process by monitoring unpaid invoices and automating reminders. It integrates with the InFakt API to retrieve invoice data and creates “cases” for each invoice that qualifies for a dunning process.

## Table of Contents
- [Overview](#overview)
- [Architecture & Technologies](#architecture--technologies)
- [Current Functionality](#current-functionality)
- [Requirements & Enhancements](#requirements--enhancements)
- [Deployment](#deployment)
- [InFakt API Integration](#infakt-api-integration)
- [Future Work](#future-work)
- [Contact](#contact)

## Overview
InvoiceTracker automates the following processes:
- **New Case Creation:** Every day, the system checks for invoices with a payment due date offset of –2 (i.e. invoices due in two days) that have not yet been paid. For these invoices, a new active case is created.
- **Active Case Updates:** The application updates the details of active cases to verify if invoices have been paid. When an invoice is fully paid, the corresponding case is automatically closed and moved to the “closed” category.
- **Automatic Email Notifications:** Based on a predefined schedule and offset values for each notification stage, email reminders are sent to clients.
- **Synchronization Status Panel:** A dashboard provides transparent details about daily synchronization activities, including numbers of new cases created, invoices updated, and cases closed.

## Architecture & Technologies
- **Backend:** Python with Flask
- **Database:** PostgreSQL using SQLAlchemy ORM
- **Scheduling:** APScheduler for running background sync and email tasks
- **Email:** SMTP (configured via environment variables)
- **Deployment:** Google Cloud (using `gcloud app deploy`)
- **External API:** InFakt API (operating under the “InFakt without accountant” plan)

## Current Functionality
- **Invoice Synchronization:**
  - **New Invoice Sync:** Queries InFakt for invoices with a payment due date in 2 days (`offset = -2`). Creates new active cases for these invoices.
  - **Active Case Update:** Updates the details of active cases only for invoices that are scheduled to receive the next notification (based on custom offset values) to avoid exceeding API rate limits.
- **Email Notifications:**
  - Uses predefined templates for various notification stages (e.g., reminder before due date, final notice, etc.).
  - Automatically sends emails in batches and logs each email dispatch.
- **Frontend:**
  - Active and closed cases are listed with detailed information such as invoice number, payment due date, amounts, client information, days past due, and progress of notifications.
  - Sorting and filtering options are available.
- **Sync Status Panel:**
  - Displays a log of recent synchronization events (number of processed invoices, duration, type of sync).

## Requirements & Enhancements
We need to improve the application based on the following key points:
1. **Efficient API Usage:**
   - Limit the daily update of active cases to only those that are scheduled to receive the next notification (to avoid unnecessary API calls).
   - Ensure that the system does not exceed the InFakt API request limits (e.g., 100 GET requests per batch).
2. **Data Completeness:**
   - Ensure that all necessary details (client tax number, email, address, etc.) are retrieved and stored correctly. Currently, some of these details are missing.
   - Verify that the function to fetch client details (e.g., "See invoice details" or "See client details") is working correctly according to InFakt API documentation.
3. **Transparent Sync Monitoring:**
   - Enhance the sync status panel to clearly display the number of new cases created, the number of cases updated, and the number of cases closed.
   - Provide real-time feedback and logging information to the user, so that they are assured of full data synchronization.
4. **Frontend Enhancements:**
   - Improve the sorting, filtering, and pagination mechanisms (e.g., 100 results per page, sort by days past due, etc.) for both active and closed cases.
   - Ensure that closed cases’ details can be viewed and are not blocked.

## Deployment
The application is deployed using Google Cloud (via `gcloud app deploy`). Environment variables for database, API keys, SMTP settings, etc., are configured in the `app.yaml` file.

## InFakt API Integration
The integration with the InFakt API is implemented through:
- **API Client:** The `InFaktAPIClient` class in `src/api/api_client.py` handles authentication and requests to InFakt.
- **Data Retrieval:** The application uses endpoints to list invoices, filter by status, and retrieve detailed client and invoice information.
- **Rate Limits:** The app is designed to work under the "InFakt without accountant" plan, with specific limits on GET requests and other operations. Detailed API documentation is provided in the project for reference.

## Future Work
- Refine the synchronization logic further to dynamically adjust API calls based on the number of active cases.
- Add additional error handling and retry logic to gracefully handle API rate limits (HTTP 429) and other errors.
- Expand the frontend dashboard for sync monitoring, possibly including graphical representations of sync metrics.

