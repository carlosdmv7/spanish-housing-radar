{#
    Select a column a relation may not have yet, typed the same either way.

    The raw tables gain columns when the loader migrates them, which happens on
    the first scrape that carries them — but `dbt build` runs on every PR and
    every scheduled run, scrape or no scrape, against the same raw tables. A
    model that names a raw column outright fails in that window. This emits
    `cast(<col> as <type>)` when the column exists and `cast(null as <type>)`
    when it does not, so the model compiles to the same column set and types
    before and after the migration, and needs no deploy ordering (ADR-0012).

    `existing` is the lower-cased list from `relation_column_names`, fetched once
    per model rather than once per column.
#}
{% macro relation_column_names(relation) %}
    {%- if not execute -%}
        {{ return([]) }}
    {%- endif -%}
    {%- set cols = adapter.get_columns_in_relation(relation) -%}
    {{ return(cols | map(attribute='name') | map('lower') | list) }}
{% endmacro %}

{% macro column_or_null(existing, column_name, data_type) -%}
    {%- if column_name | lower in existing -%}
        cast({{ column_name }} as {{ data_type }})
    {%- else -%}
        cast(null as {{ data_type }})
    {%- endif -%}
{%- endmacro %}
