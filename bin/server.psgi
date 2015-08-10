#!/usr/bin/perl
use strict;
use warnings;
use Path::Class;

$SIG{PIPE} = 'IGNORE';

require (file (__FILE__)->dir->parent->file ('schema.cgi')->stringify);

return psgi_app ();
