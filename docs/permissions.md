# Trac Permissions Guide

This guide explains which Trac permissions are required for the MCP server to function correctly, how to set them up, and how to verify your configuration.

## Overview

Trac uses a fine-grained permission system to control access to tickets and wiki pages. Each operation (viewing tickets, creating wiki pages, etc.) requires specific permissions. The MCP server needs a carefully configured service account with exactly the permissions it requires - no more, no less.

Understanding Trac permissions is essential because:
- **Too few permissions** cause the MCP server to fail when performing operations
- **Too many permissions** violate the principle of least privilege and increase security risk
- **Wrong permissions** can lead to confusing errors that are difficult to diagnose

The MCP server uses Trac's XML-RPC API, which enforces the same permission model as the web interface. Every API call checks permissions before executing.

## Required Permissions

This table shows exactly which Trac permission is required for each MCP server operation:

| Operation | Required Permission | Error When Missing |
|-----------|--------------------|--------------------|
| Query tickets | TICKET_VIEW | "Permission denied" (403) |
| Get ticket details | TICKET_VIEW | "Permission denied" (403) |
| Get ticket changelog | TICKET_VIEW | "Permission denied" (403) |
| Create ticket | TICKET_CREATE | "Permission denied: TICKET_CREATE required" |
| Update ticket | TICKET_MODIFY | "Permission denied: TICKET_MODIFY required" |
| Delete ticket | TICKET_ADMIN | "Permission denied: TICKET_ADMIN required" |
| Batch create tickets | TICKET_CREATE | "Permission denied: TICKET_CREATE required" |
| Batch update tickets | TICKET_MODIFY | "Permission denied: TICKET_MODIFY required" |
| Batch delete tickets | TICKET_ADMIN | "Permission denied: TICKET_ADMIN required" |
| List wiki pages | WIKI_VIEW | "Permission denied" (403) |
| Read wiki page | WIKI_VIEW | "Permission denied" (403) |
| Create wiki page | WIKI_CREATE | "Permission denied: WIKI_CREATE required" |
| Update wiki page | WIKI_MODIFY | "Permission denied: WIKI_MODIFY required" |
| Delete wiki page | WIKI_DELETE | "Permission denied: WIKI_DELETE required" |
| List milestones | TICKET_VIEW | "Permission denied" (403) |
| Get milestone details | TICKET_VIEW | "Permission denied" (403) |
| Create milestone | TICKET_ADMIN | "Permission denied: TICKET_ADMIN required" |
| Update milestone | TICKET_ADMIN | "Permission denied: TICKET_ADMIN required" |
| Delete milestone | TICKET_ADMIN | "Permission denied: TICKET_ADMIN required" |

## Permission Sets

### Read-Write (No Delete) -- 6 Permissions

For most use cases where you do not need delete or milestone management capabilities:

**Read Operations:**
- `TICKET_VIEW` - View tickets, search ticket database, list/get milestones
- `WIKI_VIEW` - View wiki pages and list all pages

**Write Operations:**
- `TICKET_CREATE` - Create new tickets
- `TICKET_MODIFY` - Update existing tickets (add comments, change fields)
- `WIKI_CREATE` - Create new wiki pages
- `WIKI_MODIFY` - Update existing wiki pages

The server will work with only read permissions (TICKET_VIEW and WIKI_VIEW) if you only need read-only access, but write operations will fail.

### Full Access -- 8 Permissions

For full functionality including delete tools and milestone management, add these two permissions:

- `TICKET_ADMIN` - Delete tickets, create/update/delete milestones
- `WIKI_DELETE` - Delete wiki pages

**Note:** `ticket_delete` also requires `tracopt.ticket.deleter` to be enabled in trac.ini on the Trac server.

## NOT Required

The MCP server does NOT need these permissions. Do not grant them:

- `WIKI_RENAME` - The server never renames wiki pages
- `WIKI_ADMIN` - The server does not perform wiki administration
- `TRAC_ADMIN` - The server does not perform system administration

Granting unnecessary permissions increases the attack surface if credentials are compromised.

## Setting Up Permissions

You need to create a dedicated service account for the MCP server and grant it the required permissions. Here are three approaches depending on your familiarity with Trac:

### Detailed Walkthrough (For First-Time Setup)

1. **Log in to Trac as an administrator** (you need TRAC_ADMIN permission)

2. **Navigate to the Admin panel:**
   - Click "Admin" in the top navigation bar
   - You should see the administration interface with categories like "General", "Accounts", "Permissions"

3. **Create a service account** (if you don't have one):
   - Go to "Admin" → "Accounts" → "Users"
   - Click "Add New User" or similar button
   - Username: `mcp-service-account` (or your preferred name)
   - Set a strong password
   - Do NOT use your personal account - always use a dedicated service account

4. **Grant permissions:**
   - Go to "Admin" → "Permissions"
   - Find your service account username in the list (or select it from dropdown)
   - Add the following permissions one by one:
     - TICKET_VIEW
     - TICKET_CREATE
     - TICKET_MODIFY
     - WIKI_VIEW
     - WIKI_CREATE
     - WIKI_MODIFY
   - Click "Add" or "Grant" after each permission
   - Verify all six permissions appear in the user's permission list

5. **Test the account:**
   - Log out of your admin account
   - Log in as the service account
   - Verify you can view tickets, create a test ticket, view wiki pages, and create a test wiki page
   - Log back in as admin and delete the test data

### Quick Reference (For Experienced Trac Admins)

Grant these permissions to your MCP service account for read-write access:

```
TICKET_VIEW
TICKET_CREATE
TICKET_MODIFY
WIKI_VIEW
WIKI_CREATE
WIKI_MODIFY
```

For full access (including delete and milestone management), also grant:

```
TICKET_ADMIN
WIKI_DELETE
```

You can also use `trac-admin` command line if you have shell access:

```bash
# Read-write (no delete)
trac-admin /path/to/trac permission add mcp-service-account TICKET_VIEW
trac-admin /path/to/trac permission add mcp-service-account TICKET_CREATE
trac-admin /path/to/trac permission add mcp-service-account TICKET_MODIFY
trac-admin /path/to/trac permission add mcp-service-account WIKI_VIEW
trac-admin /path/to/trac permission add mcp-service-account WIKI_CREATE
trac-admin /path/to/trac permission add mcp-service-account WIKI_MODIFY

# Full access (optional, adds delete + milestone management)
trac-admin /path/to/trac permission add mcp-service-account TICKET_ADMIN
trac-admin /path/to/trac permission add mcp-service-account WIKI_DELETE
```

### Official Documentation

For comprehensive details about Trac's permission system, see the official documentation:
- **Trac Permissions**: https://trac.edgewall.org/wiki/TracPermissions
- **Trac Admin Guide**: https://trac.edgewall.org/wiki/TracAdmin

## Security Considerations

### Principle of Minimum Privilege

Grant only the permissions required for the server to function. If you only need read-only access (viewing tickets and wiki pages), grant only TICKET_VIEW and WIKI_VIEW.

Never grant TRAC_ADMIN or other administrative permissions. The MCP server doesn't need them, and granting them means a compromised credential could modify Trac's configuration or delete data.

### Dedicated Service Account

Always use a dedicated service account for the MCP server. DO NOT use:
- Your personal Trac account
- A shared "admin" account
- An account with TRAC_ADMIN permission

Benefits of a dedicated service account:
- **Audit trail**: All MCP server actions are logged with a specific username
- **Credential rotation**: You can rotate credentials without affecting other users
- **Blast radius**: If compromised, only MCP server permissions are exposed
- **Monitoring**: You can monitor all actions by this specific account

### Credential Management

**DO:**
- Store credentials in environment variables or `.env` file
- Use different credentials for development/staging/production
- Rotate credentials periodically (every 90 days recommended)
- Use strong, unique passwords (generated, not reused)
- Restrict access to `.env` file (chmod 600 on Unix systems)

**DO NOT:**
- Commit `.env` files to git (add to `.gitignore`)
- Share credentials via email, chat, or documentation
- Use the same credentials across multiple environments
- Store credentials in source code or configuration files

Example `.env` file (never commit this):

```bash
# .env - MCP Server Credentials (NEVER COMMIT TO GIT)
TRAC_URL=https://your-trac.example.com
TRAC_USERNAME=mcp-service-account
TRAC_PASSWORD=your-secure-generated-password
TRAC_INSECURE=false  # Only true for local testing with self-signed certs
```

Add to `.gitignore`:

```
.env
.env.*
```

### Audit Logging

Trac logs all actions with the authenticated username. You can monitor MCP server activity by:

1. **Review Trac activity logs** to see all actions by the service account
2. **Set up alerts** for unusual activity (e.g., excessive ticket creation)
3. **Regular audits** to verify the service account isn't being misused

Example: Check recent activity by the service account in Trac's timeline or database logs.

### Production Deployment

When deploying the MCP server in production:
- Use environment-specific credentials (don't reuse development credentials)
- Consider using a secrets management system (AWS Secrets Manager, HashiCorp Vault)
- Implement credential rotation policies
- Monitor for failed authentication attempts (may indicate compromised credentials)
- Use HTTPS for Trac connection (never HTTP in production)

## Verification

You can verify your permission setup using either automated testing or manual checking.

### Using ping to Verify Connectivity

The simplest way to verify your credentials work is to use the `ping` MCP tool, which tests connectivity and returns the Trac API version. If `ping` succeeds, your URL and credentials are correct.

For permission-specific verification, use the manual checklist below.

### Manual Verification Checklist

If you prefer to verify manually or the automated script fails:

1. **Test TICKET_VIEW:**
   - Log in to Trac as the service account
   - Navigate to "View Tickets" or run a query
   - Verify you can see existing tickets
   - If this fails: Grant TICKET_VIEW permission

2. **Test TICKET_CREATE:**
   - Try to create a new ticket through the Trac UI
   - Fill in summary and description, click "Create"
   - Verify the ticket is created
   - If this fails: Grant TICKET_CREATE permission

3. **Test TICKET_MODIFY:**
   - Open an existing ticket
   - Add a comment or change a field
   - Click "Submit changes"
   - Verify the change is saved
   - If this fails: Grant TICKET_MODIFY permission

4. **Test WIKI_VIEW:**
   - Navigate to the wiki (usually WikiStart page)
   - Verify you can read wiki pages
   - If this fails: Grant WIKI_VIEW permission

5. **Test WIKI_CREATE:**
   - Navigate to a non-existent wiki page (e.g., "TestPage")
   - Click "Create this page"
   - Enter content and save
   - Verify the page is created
   - If this fails: Grant WIKI_CREATE permission

6. **Test WIKI_MODIFY:**
   - Open an existing wiki page
   - Click "Edit this page"
   - Make a change and save
   - Verify the change is saved
   - If this fails: Grant WIKI_MODIFY permission

Remember to clean up any test data you create during manual verification.

## Troubleshooting

### "Permission denied" errors

If you see "Permission denied" or 403 errors:
1. Check which operation failed (ticket query, wiki read, delete, etc.)
2. Look up the required permission in the table above
3. Verify the service account has that permission
4. Use the `ping` tool to verify basic connectivity

### Server works for some operations but not others

This indicates partial permission setup:
- Read operations work but write operations fail → Grant TICKET_CREATE/MODIFY and WIKI_CREATE/MODIFY
- Ticket operations work but wiki operations fail → Grant WIKI_VIEW/CREATE/MODIFY
- Wiki operations work but ticket operations fail → Grant TICKET_VIEW/CREATE/MODIFY

### "Invalid credentials" errors

This is NOT a permission issue - it's an authentication issue:
- Verify TRAC_USERNAME and TRAC_PASSWORD are correct
- Check that the account exists and is not locked
- Try logging in through Trac's web interface with the same credentials

### Delete operations fail

If delete operations fail but other write operations work:
- `ticket_delete` requires TICKET_ADMIN permission plus `tracopt.ticket.deleter` enabled in trac.ini
- `wiki_delete` requires WIKI_DELETE permission
- `milestone_delete` requires TICKET_ADMIN permission
- See the "Full Access" permission set above

## Summary

The MCP server requires six permissions for read-write functionality:
- TICKET_VIEW, TICKET_CREATE, TICKET_MODIFY
- WIKI_VIEW, WIKI_CREATE, WIKI_MODIFY

For full functionality (including delete tools and milestone management), add TICKET_ADMIN and WIKI_DELETE (eight permissions total).

Always use a dedicated service account, store credentials securely, and verify permissions before relying on the MCP server in production.

For deployment and configuration instructions, see `docs/deployment.md`.
