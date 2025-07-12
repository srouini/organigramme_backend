from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import Profile
from django import forms
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils.translation import gettext_lazy as _

User = get_user_model()

# Define available pages for selection
AVAILABLE_PAGES = [
      {
        'path': '/dashboard',
        'name': 'Dashboard',
        'children': [
          { 'path': '/dashboard', 'name': 'Dashboard'},
        ],
      },
      {
        'path': '/grades',
        'name': 'Grades',
      },
      {
        'path': '/structures',
        'name': 'structures',
      },
      {
        'path': '/positions',
        'name': 'Positions',
      },
    ]


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser')


def flatten_choices(pages, prefix=""):
    choices = []
    for page in pages:
        label = f"{prefix}{page['name']}"
        choices.append((page["path"], label))
        if "children" in page and page["children"]:
            choices.extend(flatten_choices(page["children"], prefix=prefix + "______"))
    return choices

class ProfileForm(forms.ModelForm):
    allowed_pages = forms.MultipleChoiceField(
        choices=flatten_choices(AVAILABLE_PAGES),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'allowed-pages-checkboxes',
        }),
        required=False,
        help_text='Select the pages this user can access',
    )
    class Meta:
        model = Profile
        fields = ('layout_preference', 'theme_color', 'theme_mode', 'allowed_pages')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial value for allowed_pages if instance exists
        if self.instance and self.instance.pk:
            self.initial['allowed_pages'] = self.instance.allowed_pages
        
        # Add select all button and JavaScript
        self.fields['allowed_pages'].widget.template_name = 'admin/widgets/checkbox_select_multiple_with_select_all.html'

class ProfileInline(admin.StackedInline):
    model = Profile
    form = ProfileForm
    can_delete = False
    verbose_name_plural = 'Profile'
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'allowed_pages':
            field.help_text = 'Select the pages this user can access. Home, Profile, and Settings are always accessible.'
            field.widget.attrs['style'] = 'min-width: 600px; height: 200px;'
            field.initial = Profile.DEFAULT_PAGES
        return field

    fieldsets = (
        (None, {
            'fields': ('layout_preference', 'theme_color', 'theme_mode'),
        }),
        ('Page Permissions', {
            'fields': ('allowed_pages',),
            'classes': ('wide',),
            'description': 'Select which pages this user can access. Superusers have access to all pages regardless of this setting.',
        }),
    )

class CustomUserAdmin(BaseUserAdmin):
    form = UserForm
    change_password_form = AdminPasswordChangeForm
    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_allowed_pages', 'password_change_link')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'profile__theme_mode', 'profile__layout_preference')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    filter_horizontal = ('groups', 'user_permissions',)
    
    def password_change_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:auth_user_password_change', args=[obj.pk])
        return format_html('<a class="button" href="{}">Change Password</a>', url)
    password_change_link.short_description = 'Change Password'
    password_change_link.allow_tags = True

    readonly_fields = ('password_change_link',)

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        return [
            path(
                '<id>/password/',
                self.admin_site.admin_view(self.user_change_password),
                name='auth_user_password_change',
            ),
        ] + urls

    def get_allowed_pages(self, obj):
        if obj.is_superuser:
            return 'All Pages (Superuser)'
        pages = obj.profile.allowed_pages if hasattr(obj, 'profile') else []
        if not pages:
            return 'No Pages'
        
        # Create a mapping of paths to names
        page_map = {}
        def build_page_map(pages_list):
            for page in pages_list:
                page_map[page['path']] = page['name']
                if 'children' in page and page['children']:
                    build_page_map(page['children'])
        
        build_page_map(AVAILABLE_PAGES)
        return ', '.join(page_map.get(page, page) for page in pages)
    get_allowed_pages.short_description = 'Allowed Pages'

    fieldsets = (
        (None, {'fields': ('username', 'password', 'password_change_link')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('wide',),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )

    def user_change_password(self, request, id, form_url=''):
        from django.contrib.admin.options import IS_POPUP_VAR
        from django.contrib.auth import update_session_auth_hash
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.template.response import TemplateResponse
        from django.urls import reverse
        from django.utils.html import escape

        user = self.get_object(request, id)
        if not self.has_change_permission(request, user):
            raise PermissionDenied

        if request.method == 'POST':
            form = self.change_password_form(user, request.POST)
            if form.is_valid():
                form.save()
                change_message = self.construct_change_message(request, form, None)
                self.log_change(request, user, change_message)
                msg = _('Password changed successfully.')
                messages.success(request, msg)
                update_session_auth_hash(request, form.user)
                return HttpResponseRedirect(
                    reverse(
                        '%s:%s_%s_change' % (
                            self.admin_site.name,
                            user._meta.app_label,
                            user._meta.model_name,
                        ),
                        args=(user.pk,),
                    )
                )
        else:
            form = self.change_password_form(user)

        fieldsets = [(None, {'fields': list(form.base_fields)})]
        adminForm = admin.helpers.AdminForm(form, fieldsets, {})

        context = {
            'title': _('Change password: %s') % escape(user.get_username()),
            'adminForm': adminForm,
            'form_url': form_url,
            'form': form,
            'is_popup': (IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET),
            'is_popup_var': IS_POPUP_VAR,
            'add': True,
            'change': False,
            'has_delete_permission': False,
            'has_change_permission': True,
            'has_absolute_url': False,
            'opts': self.model._meta,
            'original': user,
            'save_as': False,
            'show_save': True,
            **self.admin_site.each_context(request),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.change_user_password_template or
            'admin/auth/user/change_password.html',
            context,
        )

class ProfileAdmin(admin.ModelAdmin):
    form = ProfileForm
    list_display = ('user', 'layout_preference', 'theme_mode', 'get_allowed_pages')
    list_filter = ('layout_preference', 'theme_mode')
    search_fields = ('user__username', 'user__email')
    ordering = ('user__username',)

    def get_allowed_pages(self, obj):
        if obj.user.is_superuser:
            return 'All Pages (Superuser)'
        if not obj.allowed_pages:
            return 'No Pages'
        
        # Create a mapping of paths to names
        page_map = {}
        def build_page_map(pages_list):
            for page in pages_list:
                page_map[page['path']] = page['name']
                if 'children' in page and page['children']:
                    build_page_map(page['children'])
        
        build_page_map(AVAILABLE_PAGES)
        return ', '.join(page_map.get(page, page) for page in obj.allowed_pages)
    get_allowed_pages.short_description = 'Allowed Pages'

    fieldsets = (
        (None, {
            'fields': ('user', 'layout_preference', 'theme_color', 'theme_mode'),
        }),
        ('Page Permissions', {
            'fields': ('allowed_pages',),
            'classes': ('wide',),
            'description': 'Select which pages this user can access. Superusers have access to all pages regardless of this setting.',
        }),
    )

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Profile, ProfileAdmin)