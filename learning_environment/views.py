from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views import generic
from django.http import HttpResponseBadRequest, HttpResponseServerError
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from .forms import *
from .models import Lesson, Task, Solution, LearnerStatus, Profile, User
from .its.tutormodel import Tutormodel, NoTaskAvailableError
from .its.learnermodel import Learnermodel


class SignUpView(SuccessMessageMixin, generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"
    success_message = "User was created successfully. You may now log in."

@login_required
def practice(request):
    """Display a task for practicing."""

    context = {'mode': 'solve'}

    # start a lesson
    if request.method == 'POST' and 'start' in request.POST:
        if not 'current_lesson_todo' in request.session:  # if there's no todo, we have a corrupt state -> show start screen
            return redirect('myhome')
        request.session['current_lesson_todo'].pop(0)  # remove the start item
        request.session.modified = True
        tutor = Tutormodel(request.user)
        try:
            (state, lesson, task) = tutor.next_task(request)
        except NoTaskAvailableError:
            return HttpResponseServerError("Error: No task available!")
        context['state'] = state
    # finish a lesson
    elif request.method == 'POST' and 'finish' in request.POST:
        if not 'current_lesson_todo' in request.session:  # if there's no todo, we have a corrupt state -> show start screen
            # TODO: message
            return redirect('myhome')
        if request.session['current_lesson_todo'][0] != 'WRAPUP':  # if we didn't finish a lesson, we have corrupt state
            # TODO: message
            return redirect('myhome')
        request.user.profile.level += 1  # advance a level
        request.user.save()
        return redirect('myhome')
    # analyze a solution
    elif request.method == 'POST':
        try:
            task = Task.objects.get(pk=int(request.POST['task']))
        except (KeyError, Task.DoesNotExist):
            return HttpResponseBadRequest("Invalid Task ID")
        # Evaluate solution
        learnermodel = Learnermodel(request.user)
        analysis, learnermodel_context = learnermodel.update(task, request.POST)
        context.update(learnermodel_context)
        if analysis.get('solved', False):  # we solved a task, so we remove its type from the session todo list
            request.session['current_lesson_todo'].pop(0)
            request.session.modified = True

        lesson = task.lesson
        context['state'] = context['mode']
    elif 'redo' in request.GET:  # show a task again
        try:
            task = Task.objects.get(pk=int(request.GET['redo']))
        except KeyError:
            return HttpResponseBadRequest("Error: No such ID")
        lesson = task.lesson
        context['state'] = context['mode']
    else:  # fetch new task and show it
        tutor = Tutormodel(request.user)
        try:
            (state, lesson, task) = tutor.next_task(request)
        except NoTaskAvailableError:
            return HttpResponseServerError("Error: No task available!")
        context['state'] = state

    context['task'] = task
    context['lesson'] = lesson
    # Pass all information to template and display page
    return render(request, 'learning_environment/task.html', context=context)


# basic view login NOT required
def home(request):
    page = 'home'  # for highlighting current page
    if request.user.is_authenticated:
        return redirect('myhome')
    return render(request, 'learning_environment/home.html', locals())


# basic view for authenticated users
def myhome(request):
    page = 'myhome'  # for highlighting current page
    try:
        request.user.save()
    except Profile.DoesNotExist:
        p = Profile(user=request.user)
        p.save()
    try:
        del request.session['current_lesson']
    except KeyError:
        pass
    try:
        del request.session['current_lesson_todo']
    except KeyError:
        pass
    levels = Lesson.objects.all().order_by('lesson_id')
    return render(request, 'learning_environment/myhome.html', locals())


class TaskListView(ListView):
    """List all tasks"""
    model = Task
    paginate_by = 25  # 25 entries max per page

    def get_ordering(self):
        ordering = self.request.GET.get('ordering', 'lesson__name')
        # validate ordering here
        return ordering


class LessonDetailView(DetailView):
    """Show details for a single lesson (esp. JSON5)"""
    model = Lesson

class LessonCreateView(FormView):

    def post(self, request):
        form = LessonCreationForm(request.POST)
        if form.is_valid():
            l = Lesson.create_from_json5(form.cleaned_data.get('json5'))
            messages.info(request, "Lesson {} successfully created.".format(l.lesson_id))
            return redirect('home')
        else:
            msg = form.errors
        return render(request, 'learning_environment/lesson_form.html', locals())
    def get(self, reguest):
        form = LessonCreationForm()
        return render(reguest, 'learning_environment/lesson_form.html', locals())

def learner_dashboard(request):
    """Prepare data for learner's own dashboard and show it."""
    solutions = Solution.objects.filter(user=request.user).order_by('timestamp')  # all solutions from current user
    num_tasks = solutions.count()  # how tasks did this user try
    correct_solutions = Solution.objects.filter(user=request.user, solved=True).count()  # how many of them were correct?
    if num_tasks > 0:  # calculate percentage of correct tasks (or 0 if no tasks)
        tasks_correctness = correct_solutions / num_tasks * 100.0
    else:
        tasks_correctness = 0.0
    return render(request, 'learning_environment/learner_dashboard.html', locals())  # pass all local variable to template

def global_dashboard(request):
    solutions = Solution.objects.all().order_by('timestamp')  # all solutions
    num_solutions = solutions.count()  # how tasks did this user try
    correct_solutions = Solution.objects.filter(solved=True).count()  # how many of them were correct?
    if num_solutions > 0:  # calculate percentage of correct tasks (or 0 if no tasks)
        tasks_correctness = correct_solutions / num_solutions * 100.0
    else:
        tasks_correctness = 0.0
    return render(request, 'learning_environment/global_dashboard.html', locals())  # pass all local variable to template


def learner_reset(request):
    if request.user.is_authenticated:
        request.user.profile.level = 0
        request.user.save()
        messages.info(request, "Levels have been reset for user {}".format(request.user.username))
        return redirect("myhome")
    else:
        return redirect("home")
