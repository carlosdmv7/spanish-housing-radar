-- transform/macros/price_per_sqm.sql
{% macro price_per_sqm(price_col, size_col) %}
    case
        when {{ size_col }} > 0
        then round({{ price_col }} / nullif({{ size_col }}, 0), 2)
        else null
    end
{% endmacro %}