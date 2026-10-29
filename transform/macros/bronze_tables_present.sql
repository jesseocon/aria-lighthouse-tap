{#- Which of a hotel's bronze tables exist, logged as one JSON line the
    connector reads before dbt run: `BRONZE_PRESENT: ["..._rates_v2_hotel_1"]`.
    dbt then builds only the models those tables feed. A dataset that does
    not exist yet lists no tables. -#}
{% macro bronze_tables_present(project, dataset, tables) %}
  {% if execute %}
    {% set schema = api.Relation.create(database=project, schema=dataset) %}
    {% set listed = adapter.list_relations_without_caching(schema) | map(attribute='identifier') | list %}
    {% set present = [] %}
    {% for table_name in tables if table_name in listed %}
      {% do present.append(table_name) %}
    {% endfor %}
    {{ log("BRONZE_PRESENT: " ~ tojson(present | sort), info=true) }}
  {% endif %}
{% endmacro %}
