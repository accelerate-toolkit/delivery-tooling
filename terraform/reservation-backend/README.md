# Reservation backend

Deploy this module once per administrative boundary. Share the table across
products and components; each item key is `environment/product`. Consumers require
`dynamodb:DescribeTable`, `dynamodb:GetItem` and `dynamodb:PutItem`. Restrict item
access with `ForAllValues:StringEquals` on `dynamodb:LeadingKeys` where appropriate;
DescribeTable requires its own statement. Operators performing recovery need the
same item permissions. No table creation or deletion permission belongs to clients.

The table uses on-demand billing, encryption, point-in-time recovery and deletion
protection. It deliberately has **no TTL**. An expired record must remain until an
operator reconciles any outstanding processes and cloud operations. Disabling or
deleting this table, restoring an older snapshot, or changing its name requires
quiescing every consumer first. Restoring old lock state while clients run is unsafe.

Infrastructure owners choose provider/region, table name, tags, state backend and
IAM principals. This module does not grant permissions or own credentials.
