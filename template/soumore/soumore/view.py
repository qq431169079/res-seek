#!/usr/bin/env pytho
# -*- coding: utf-8 -*-
"""
author:smater
"""
from django.shortcuts import render

def hello(request):
    context = {}
    context['hello'] = 'hello world!'
    return render(render, 'hello.html', context)


