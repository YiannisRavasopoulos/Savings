-- Archived categories carry "(archived)" in their name, so the original name is free to reuse.
UPDATE categories
   SET name = CASE
         WHEN EXISTS (SELECT 1 FROM categories o WHERE o.user_id = categories.user_id AND o.id != categories.id
                       AND o.name = categories.name || ' (archived)' COLLATE NOCASE)
         THEN categories.name || ' (archived ' || categories.id || ')'
         ELSE categories.name || ' (archived)' END
 WHERE archived = 1 AND name NOT LIKE '% (archived%';
