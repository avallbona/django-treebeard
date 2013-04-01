"""Forms for treebeard."""

from django import forms
from django.db.models.query import QuerySet
from django.forms.models import BaseModelForm, ErrorList, model_to_dict
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _


class MoveNodeForm(forms.ModelForm):
    """
    Form to handle moving a node in a tree.

    Handles sorted/unsorted trees.
    """

    __position_choices_sorted = (
        ('sorted-child', _('Child of')),
        ('sorted-sibling', _('Sibling of')),
    )

    __position_choices_unsorted = (
        ('first-child', _('First child of')),
        ('left', _('Before')),
        ('right', _('After')),
    )

    _position = forms.ChoiceField(required=True, label=_("Position"))

    _ref_node_id = forms.TypedChoiceField(required=False,
                                          coerce=int,
                                          label=_("Relative to"))

    class Meta:
        exclude = ('path',
                   'depth',
                   'numchild',
                   'lft',
                   'rgt',
                   'tree_id',
                   'parent',
                   'sib_order')

    def _get_position_ref_node(self, instance):
        if self.is_sorted:
            position = 'sorted-child'
            node_parent = instance.get_parent()
            if node_parent:
                ref_node_id = node_parent.pk
            else:
                ref_node_id = ''
        else:
            prev_sibling = instance.get_prev_sibling()
            if prev_sibling:
                position = 'right'
                ref_node_id = prev_sibling.pk
            else:
                position = 'first-child'
                if instance.is_root():
                    ref_node_id = ''
                else:
                    ref_node_id = instance.get_parent().pk
        return {'_ref_node_id': ref_node_id,
                '_position': position}

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=':',
                 empty_permitted=False, instance=None):
        opts = self._meta
        if instance:
            opts.model = type(instance)
        self.is_sorted = getattr(opts.model, 'node_order_by', False)

        if self.is_sorted:
            choices_sort_mode = self.__class__.__position_choices_sorted
        else:
            choices_sort_mode = self.__class__.__position_choices_unsorted
        self.declared_fields['_position'].choices = choices_sort_mode

        if instance is None:
            # if we didn't get an instance, instantiate a new one
            instance = opts.model()
            object_data = {}
            choices_for_node = None
        else:
            object_data = model_to_dict(instance, opts.fields, opts.exclude)
            object_data.update(self._get_position_ref_node(instance))
            choices_for_node = instance

        choices = self.mk_dropdown_tree(opts.model, for_node=choices_for_node)
        self.declared_fields['_ref_node_id'].choices = choices
        self.instance = instance
        # if initial was provided, it should override the values from instance
        if initial is not None:
            object_data.update(initial)
        super(BaseModelForm, self).__init__(data, files, auto_id, prefix,
                                            object_data, error_class,
                                            label_suffix, empty_permitted)

    def _clean_cleaned_data(self):
        """ delete auxilary fields not belonging to node model """
        reference_node_id = 0

        if '_ref_node_id' in self.cleaned_data:
            reference_node_id = self.cleaned_data['_ref_node_id']
            del self.cleaned_data['_ref_node_id']

        position_type = self.cleaned_data['_position']
        del self.cleaned_data['_position']

        return position_type, reference_node_id

    def save(self, commit=True):
        position_type, reference_node_id = self._clean_cleaned_data()

        if self.instance.pk is None:
            cl_data = {}
            for field in self.cleaned_data:
                if not isinstance(self.cleaned_data[field], (list, QuerySet)):
                    cl_data[field] = self.cleaned_data[field]
            if reference_node_id:
                reference_node = self.Meta.model.objects.get(
                    pk=reference_node_id)
                self.instance = reference_node.add_child(**cl_data)
                self.instance.move(reference_node, pos=position_type)
            else:
                self.instance = self.Meta.model.add_root(**cl_data)
        else:
            self.instance.save()
            if reference_node_id:
                reference_node = self.Meta.model.objects.get(
                    pk=reference_node_id)
                self.instance.move(reference_node, pos=position_type)
            else:
                if self.is_sorted:
                    pos = 'sorted-sibling'
                else:
                    pos = 'first-sibling'
                self.instance.move(self.Meta.model.get_first_root_node(), pos)
        # Reload the instance
        self.instance = self.Meta.model.objects.get(pk=self.instance.pk)
        super(MoveNodeForm, self).save(commit=commit)
        return self.instance

    @staticmethod
    def is_loop_safe(for_node, possible_parent):
        if for_node is not None:
            return not (
                possible_parent == for_node
                ) or (possible_parent.is_descendant_of(for_node))
        return True

    @staticmethod
    def mk_indent(level):
        return '&nbsp;&nbsp;&nbsp;&nbsp;' * (level - 1)

    @classmethod
    def add_subtree(cls, for_node, node, options):
        """ Recursively build options tree. """
        if cls.is_loop_safe(for_node, node):
            options.append(
                (node.pk,
                 mark_safe(cls.mk_indent(node.get_depth()) + str(node))))
            for subnode in node.get_children():
                cls.add_subtree(for_node, subnode, options)

    @classmethod
    def mk_dropdown_tree(cls, model, for_node=None):
        """ Creates a tree-like list of choices """

        options = [(0, _('-- root --'))]
        for node in model.get_root_nodes():
            cls.add_subtree(for_node, node, options)
        return options

