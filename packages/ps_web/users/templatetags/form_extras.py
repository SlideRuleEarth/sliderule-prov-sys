from django import template
from django.forms import Form

register = template.Library()

@register.filter(name='add_disabled')
def add_disabled(form: Form):
    for field_name in form.fields:
        field = form.fields[field_name]
        attrs = field.widget.attrs
        attrs.update({'disabled': 'disabled'})
    return form
