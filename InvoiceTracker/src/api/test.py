import logging
from api_client import InFaktAPIClient 

# def test_list_invoices(api_client):
#     print("Testing list_invoices...")
#     invoices = api_client.list_invoices(offset=0, limit=5)
#     if invoices:
#         print(f"Found {len(invoices)} invoices:")
#         for invoice in invoices:
#             print(invoice)
#     else:
#         print("No invoices found or an error occurred.")

# def test_list_active_invoices(api_client):
#     print("Testing list_active_invoices...")
#     active_invoices = api_client.list_active_invoices(offset=0, limit=5)
#     if active_invoices:
#         print(f"Found {len(active_invoices)} active invoices:")
#         for invoice in active_invoices:
#             print(invoice)
#     else:
#         print("No active invoices found or an error occurred.")

# def test_list_clients(api_client):
#     print("Testing list_clients...")
#     clients = api_client.list_clients(offset=0, limit=5)
#     if clients:
#         print(f"Found {len(clients)} clients:")
#         for client in clients:
#             print(client)
#     else:
#         print("No clients found or an error occurred.")

def test_get_client_details(api_client, client_id):
    print(f"Testing get_client_details for client_id {client_id}...")
    client_details = api_client.get_client_details(client_id)
    if client_details:
        print(f"Client details for client_id {client_id}:")
        print(client_details)
    else:
        print(f"No details found for client_id {client_id} or an error occurred.")

if __name__ == "__main__":
    # Initialize the InFaktAPIClient
    try:
        api_client = InFaktAPIClient()
        print("InFaktAPIClient initialized successfully!")
    except ValueError as e:
        print(f"Error initializing InFaktAPIClient: {e}")
        exit(1)

    # # Test API methods
    # test_list_invoices(api_client)
    # test_list_active_invoices(api_client)
    # test_list_clients(api_client)

    # Replace with a valid client ID for testing
    client_id_to_test = 19357911  # Replace this with an actual client ID to test the get_client_details method
    test_get_client_details(api_client, client_id_to_test)
