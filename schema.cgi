#!/usr/bin/perl
use strict;

use lib qw[/home/httpd/html/www/markup/html/whatpm
           /home/wakaba/work/manakai2/lib];
use CGI::Carp qw[fatalsToBrowser];
require Message::CGI::Carp;

my $data_directory = './data/';
my $map_directory = $data_directory;
my $DEBUG = 1;

use Encode;
use Message::URI::URIReference;
use Message::CGI::HTTP;
my $cgi = Message::CGI::HTTP->new;

print "Cache-Control: no-cache\n" if $DEBUG;

my $path = $cgi->path_info;
$path = '' unless defined $path;

my @path = split m#/#, percent_decode ($path), -1;

if (@path == 3 and $path[0] eq '' and $path[1] =~ /\A[0-9a-f]+\z/) {
  if ($path[2] eq 'cache.dat') {
    my $file_text = get_file_text ($path[1]);
    if (defined $file_text) {
      my $prop = get_prop_hash ($path[1]);
      print "Status: 203 Non-Authoritative Information\n";
      my $ct = $prop->{content_type}->[0]
          ? $prop->{content_type}->[0]->[0]
          : 'application/octet-stream';
      $ct =~ s/[\x09\x0A\x0D]+/ /g;
      $ct =~ s/[^\x20-\x7E]+//g;
      print "Content-Type: $ct\n";
      my $file_name = $prop->{file_name}->[0]
          ? $prop->{file_name}->[0]->[0] : '';
      $file_name =~ s/[\x09\x0A\x0D]+/ /g;
      $file_name =~ s/[^\x20-\x7E]+//g;
      if (length $file_name) {
        $file_name =~ s/\\/\\\\/g;
        $file_name =~ s/"/\\"/g;
        print qq[Content-Disposition: inline; filename="$file_name"\n];
      }
      my $uri = $prop->{base_uri}->[0] ? $prop->{base_uri}->[0]->[0] : '';
      if (length $uri) {
        print q[Content-Location: ];
        print Message::DOM::DOMImplementation->create_uri_reference ($uri)
            ->get_uri_reference->uri_reference;
        print "\n";
      }
      my $lm = $prop->{last_modified}->[0]
          ? rfc3339_to_http ($prop->{last_modified}->[0]->[0]) : '';
      if (length $lm) {
        print "Last-Modified: Mon, $lm\n";
        ## NOTE: Weekday is not a matter, since Apache rewrites it.
      }
      print "\n";
      print $file_text;
      exit;      
    }    
  } elsif ($path[2] eq 'cache.html') {
    my $file_text = get_file_text ($path[1]);
    if (defined $file_text) {
      my $prop = get_prop_hash ($path[1]);
      my ($title_text, $title_lang) = get_title_prop_text ($prop);
      $title_text = htescape ($title_text);
      $title_lang = htescape ($title_lang);

      print "Content-Type: text/html; charset=utf-8\n\n";
      binmode STDOUT, ':utf8';
      print qq[<!DOCTYPE HTML>
<html lang="en">
<head>
<title lang="$title_lang">$title_text</title>
<link rel=stylesheet href="/www/style/html/xhtml">
<style>
  pre {
    counter-reset: line;
  }
  span.line {
    display: inline;
    white-space: -moz-pre-wrap;
    white-space: pre-wrap;
  }
  .line:before {
    content: counter(line) ".\\A0";
    counter-increment: line;
  }
</style>
</head>
<body>
<h1 lang="$title_lang">$title_text</h1>

<pre><code>];
      for (split /\x0D?\x0A/, $file_text) {
        print qq[<span class=line>], htescape ($_), qq[</span>\n];
      }
      print qq[</code></pre>

<div class=navigation>
[<a href="../list.html">List</a>]
[<a href="../../schema-add">Add</a>]
[<a href="prop.html">Information</a>
<a href="propedit.html">Edit Information</a>]
[<a href="cache.dat">Cache (as is)</a>
<a>Cache (annotated)</a>]
</div>
</body>
</html>];
      exit;      
    }    
  } elsif ($path[2] eq 'prop.txt') {
    if ($cgi->request_method eq 'PUT') {
      ## TODO: CONTENT_TYPE check
      my $prop_text = Encode::decode ('utf8', $cgi->entity_body);
      if (set_prop_text ($path[1], $prop_text, new_file => 0)) {
        my $prop = get_prop_hash ($path[1]);
        update_maps ($path[1] => $prop);

        print "Status: 201 Created\nContent-Type: text/plain\n\n201";
        ## TODO: Is this status code OK?
      }
    } else {
      my $prop_text = get_prop_text ($path[1]);
      if (defined $prop_text) {
        print "Content-Type: text/plain; charset=utf-8\n\n";
        binmode STDOUT, ':utf8';
        print $prop_text;
        exit;
      }
    }
  } elsif ($path[2] eq 'prop.html') {
    my $prop = get_prop_hash ($path[1]);
    if (keys %$prop) {
      print "Content-Type: text/html; charset=utf-8\n\n";
      binmode STDOUT, ':utf8';

      my ($title_text, $title_lang) = get_title_prop_text ($prop);
      $title_text = htescape ($title_text);
      $title_lang = htescape ($title_lang);

      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title lang="$title_lang">$title_text &mdash; Information</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1 lang="$title_lang">$title_text &mdash; Information</h1>
];

      my %keys = map {$_ => 1} keys %$prop;

      print qq[<dl>];
      print qq[<dt lang="en">URI</dt>];
      for my $v (@{$prop->{uri}}) {
        my $uri = $v->[0];
        my $etime = '';
        if ($uri =~ s/<>(.*)$//s) {
          $etime = htescape ($1);
        }
        my $euri = htescape ($uri);
        my $elang = htescape ($v->[1]);
        print qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">$euri</a>&gt;</code>];

        my $uri2 = Message::DOM::DOMImplementation->create_uri_reference
            (q<../uri.html>);
        $uri2->uri_query ($uri);
        print qq[ [<a href="@{[htescape ($uri2->uri_reference)]}" lang="en">more</a>]];

        if (length $etime) {
          print qq[ (<time>$etime</time>)];
        }
        print qq[</dd>];
      }
      delete $keys{uri};

      if (keys %keys) {
        for my $key (sort {$a cmp $b} keys %keys) {
          next unless @{$prop->{$key}};
          print qq[<dt>], htescape ($key), qq[</dt>];
          for (@{$prop->{$key}}) {
            print qq[<dd lang="@{[htescape ($_->[1])]}">],
                htescape ($_->[0]), qq[</dd>\n];
          }
        }
      }
      
      print qq[</dl>];
      print qq[

<div class=navigation lang=en>
[<a href="../list.html">List</a>]
[<a href="../../schema-add">Add</a>]
[<a>Information</a>
<a href="propedit.html">Edit Information</a>]
[<a href="cache.dat">Cache (as is)</a>
<a href="cache.html">Cache (annotated)</a>]
</div>

</body>
</html>];
      exit;
    }
  } elsif ($path[2] eq 'propedit.html') {
    print 'Location: ' . $cgi->script_name . "/../prop-edit\n\n";
    exit;
  }
} elsif (@path == 2 and $path[0] eq '' and $path[1] eq '') {
  if ($cgi->request_method eq 'POST') {
    my $uri = $cgi->get_parameter ('uri');
    if (defined $uri) {
      my $ent = get_remote_entity ($uri);
      if (defined $ent->{s}) {
        my $digest = get_digest ($ent->{s});
        my $prop = get_prop_hash ($digest);
        unless (keys %$prop) {
          ## New file
          set_file_text ($digest => $ent->{s});
        }
        add_prop ($prop, 'uri', $ent->{uri}.'<>'.time_to_rfc3339 (time), '');
        add_prop ($prop, 'base_uri', $ent->{base_uri}, '');
        add_prop ($prop, 'content_type', $ent->{media_type}, '');
        add_prop ($prop, 'charset', $ent->{charset}, '')
            if defined $ent->{charset};
        for (@{$ent->{header_field}}) {
          my ($n, $v) = (lc $_->[0], $_->[1]);
          if ($n eq 'last-modified') {
            my $lm = http_to_rfc3339 ($v);
            if (length $lm) {
              add_prop ($prop, 'last_modified', $lm, '');
            }
          }
        }
        set_prop_hash ($digest => $prop);

        update_maps ($digest, $prop);

        print "Status: 201 Created\n";
        print "Content-Type: text/html; charset=iso-8859-1\n";
        my $uri = Message::DOM::DOMImplementation->create_uri_reference
            ($digest . q</prop.html>)
            ->get_absolute_reference ($cgi->request_uri)
            ->get_uri_reference
            ->uri_reference;
        print "Location: $uri\n";
        print "\n";
        my $euri = htescape ($uri);
        print qq[<a href="$euri">$euri</a>];
        exit;
      } else {
        print "Status: 400 Specified URI cannot be dereferenced\n";
        print "Content-Type: text/plain; charset=iso-8859-1\n\n";
        print "Specified URI Cannot Be Dereferenced\n";
        print "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n";
        for my $key (sort {$a cmp $b} keys %$ent) {
          print $key, "\t", $ent->{$key}, "\n";
        }
        exit;
      }
    } else {
      print "Status: 400 No uri Parameter Specified\n";
      print "Content-Type: text/plain\n\n400";
      exit;
    }
  } else {
    print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
    exit;
  }
} elsif (@path == 2 and $path[0] eq '' and $path[1] eq 'list.html') {
  print "Content-Type: text/html; charset=utf-8\n";
  binmode STDOUT, ':utf8';
  print "\n";
  print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of URIs in the HTML Schema Database</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>List of URIs in the HTML Schema Database</h1>
<ul>];

  my $uri_list = get_map ('uri_to_entity');
  for (sort {$a cmp $b} keys %$uri_list) {
    my $euri = htescape ($_);
    my $uri2 = Message::DOM::DOMImplementation->create_uri_reference
        (q<uri.html>);
    $uri2->uri_query ($_);
    my $euri2 = htescape ($uri2);
    print qq[<li><code class=uri lang=en>&lt;<a href="$euri2">$euri</a>&gt;</code></li>];
  }
  print qq[</ul>

<div class=navigation lang=en>
[<a>List</a>]
[<a href="../schema-add">Add</a>]
</div>
</body></html>];
  exit;
} elsif (@path == 3 and $path[0] eq '' and $path[1] eq 'list' and
    $path[2] eq 'pubid.html') {
  my $query = $cgi->query_string;

  if (defined $query) {
    print "Content-Type: text/html; charset=utf-8\n";
    binmode STDOUT, ':utf8';
    print "\n";
    
    $query = '?' . $query;
    my $turi = Message::DOM::DOMImplementation->create_uri_reference ($query)
        ->get_iri_reference
        ->uri_query;
    $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
    my $eturi = htescape ($turi);
    
    print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with "$eturi"</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with <code>$eturi</code></h1>
<ul>];

    my $uri_to_entity = get_map ('pubid_to_entity')->{$turi};
    for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
      my $edigest = htescape ($digest);
      my $uri2 = Message::DOM::DOMImplementation->create_uri_reference
          (q<../> . $digest . q</prop.html>);
      my $euri2 = htescape ($uri2);
      print qq[<li><a href="$euri2"><code lang="">$edigest</code></a></li>];
    }
    print qq[</ul>
             
<div class=navigation lang=en>
[<a href="list.html">List</a>]
[<a href="../schema-add">Add</a>]
</div>
</body></html>];
    exit;
  } else {
    print "Content-Type: text/html; charset=utf-8\n";
    binmode STDOUT, ':utf8';
    print "\n";
    print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of Public Identifiers in the HTML Schema Database</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>List of Public Identifiers in the HTML Schema Database</h1>
<ul>];

    my $uri_list = get_map ('pubid_to_entity');
    for (sort {$a cmp $b} keys %$uri_list) {
      my $euri = htescape ($_);
      my $uri2 = Message::DOM::DOMImplementation->create_uri_reference
          (q<pubid.html>);
      $uri2->uri_query ($_);
      my $euri2 = htescape ($uri2);
      print qq[<li><a href="$euri2"><code lang=en class=public-id>$euri</code></a></li>];
    }
    print qq[</ul>

<div class=navigation lang=en>
[<a>List</a>]
[<a href="../schema-add">Add</a>]
</div>
</body></html>];
    exit;
  }
} elsif (@path == 2 and $path[0] eq '' and $path[1] eq 'uri.html') {
  print "Content-Type: text/html; charset=utf-8\n";
  binmode STDOUT, ':utf8';
  print "\n";

  my $query = $cgi->query_string;
  if (defined $query) {
    $query = '?' . $query;
  } else {
    $query = '';
  }
  my $turi = Message::DOM::DOMImplementation->create_uri_reference ($query)
      ->get_iri_reference
      ->uri_query;
  $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
  my $eturi = htescape ($turi);

  print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with &lt;$eturi&gt;</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with <code>&lt;$eturi&gt;</code></h1>
<ul>];

  my $uri_to_entity = get_map ('uri_to_entity')->{$turi};
  for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
    my $edigest = htescape ($digest);
    my $uri2 = Message::DOM::DOMImplementation->create_uri_reference
        ($digest . q</prop.html>);
    my $euri2 = htescape ($uri2);
    print qq[<li><a href="$euri2"><code lang="">$edigest</code></a></li>];
  }
  print qq[</ul>

<div class=navigation lang=en>
[<a href="list.html">List</a>]
[<a href="../schema-add">Add</a>]
</div>
</body></html>];
  exit;
}

print "Status: 404 Not Found\nContent-Type: text/plain\n\n404";
exit;

sub percent_decode ($) {
  return Message::DOM::DOMImplementation->create_uri_reference ($_[0])
      ->get_iri_reference
      ->uri_reference;
} # percent_decode

sub htescape ($) {
  my $s = shift;
  $s =~ s/&/&amp;/g;
  $s =~ s/</&lt;/g;
  $s =~ s/>/&gt;/g;
  $s =~ s/"/&quot;/g;
  return $s;
} # htescape

sub get_digest ($) {
  require Digest::MD5;
  my $v = $_[0];
  $v =~ s/\x0D\x0A/\x0A/g;
  $v =~ tr/\x0D/\x0A/;
  return Digest::MD5::md5_hex ($v);
} # get_digest

sub get_file_text ($) {
  my $file_name = $data_directory . $_[0] . '.dat';
  if (-f $file_name) {
    open my $file, '<', $file_name or die "$0: $file_name: $!";
    local $/ = undef;
    return <$file>;
  } else {
    return undef;
  }
} # get_file_text

sub set_file_text ($$) {
  my $file_name = $data_directory . $_[0] . '.dat';
  if (-f $file_name) {
    die "$0: $file_name: File exists";
  } else {
    open my $file, '>', $file_name or die "$0: $file_name: $!";
    print $file $_[1];
  }
} # set_file_text

sub get_prop_text ($) {
  my $file_name = $data_directory . $_[0] . '.prop';
  if (-f $file_name) {
    open my $file, '<:utf8', $file_name or die "$0: $file_name: $!";
    local $/ = undef;
    return <$file>;
  } else {
    return undef;
  }
} # get_prop_text

sub set_prop_text ($$;%) {
  my %opt = @_[2,$#$_];

  my $file_name = $data_directory . $_[0] . '.prop';
  unless ($opt{new_file}) {
    return 0 unless -f $file_name;
  }

  open my $file, '>:utf8', $file_name or die "$0: $file_name: $!";
  print $file $_[1];
  return 1;
} # set_prop_text

sub get_prop_hash ($) {
  my $prop_text = get_prop_text ($_[0]);
  my $r = {};
  for (split /\x0D?\x0A/, $prop_text) {
    if (/:/) {
      my ($n, $v) = split /\s*:\s*/, $_, 2;
      my $lang = '';
      if ($n =~ s/\@([^@]*)$//) {
        $lang = $1;
      }
      $v =~ s/\\n/\x0A/g;
      $v =~ s/\\\\/\\/g;
      push @{$r->{$n} ||= []}, [$v, $lang];
    } elsif (length $_) {
      push @{$r->{$_} ||= []}, ['', ''];
    }
  }
  return $r;
} # get_prop_hash

sub set_prop_hash ($$) {
  my $hash = $_[1];
  my $r = '';
  for my $n (sort {$a cmp $b} keys %$hash) {
    my $key = $n;
    for (@{$hash->{$key}}) {
      $n =~ tr/\x0D\x0A//d;
      my $lang = $_->[1];
      $lang =~ tr/\x0D\x0A//d;
      my $v = $_->[0];
      $v =~ s/\\/\\\\/g;
      $v =~ s/\x0D?\x0A/\\n/g;
      $v =~ s/\x0D/\\n/g;
      $r .= $n . '@' . $lang . ':' . $v . "\x0A";
    }
  }
  return set_prop_text ($_[0] => $r, new_file => 1);
} # set_prop_hash

sub get_title_prop_text ($) {
  my $prop = shift;
  if ($prop->{title}->[0]) {
    return @{$prop->{title}->[0]};
  } elsif ($prop->{file_name}->[0]) {
    return @{$prop->{file_name}->[0]};
  } elsif ($prop->{public_id}->[0]) {
    return @{$prop->{public_id}->[0]};
  } elsif ($prop->{system_id}->[0]) {
    return @{$prop->{system_id}->[0]};
  } elsif ($prop->{uri}->[0]) {
    my ($v, $l) = @{$prop->{uri}->[0]};
    $v =~ s/<>.*$//s;
    return ($v, $l);
  } else {
    return ('', '');
  }
} # get_title_prop_text

sub add_prop ($$$$) {
  my ($prop, $key) = ($_[0], $_[1]);
  $prop->{$key} ||= [];
  for (@{$prop->{$key}}) {
    if ($_->[0] eq $_[2] and $_->[1] eq $_[3]) {
      return;
    }
  }
  push @{$prop->{$key}}, [$_[2], $_[3]];
} # add_prop

sub get_map ($) {
  my $file_name = $map_directory . $_[0] . '.map';
  if (-f $file_name) {
    return do $file_name;
  } else {
    return {};  
  }
} # get_map

sub set_map ($$) {
  my $file_name = $map_directory . $_[0] . '.map';
  require Data::Dumper;
  open my $file, '>', $file_name or die "$0: $file_name: $!";
  print $file Data::Dumper::Dumper ($_[1]);
  return 1;
} # set_map

sub update_maps ($$) {
  my ($digest, $prop) = @_;
  
  my $uri_to_entity = get_map ('uri_to_entity');
  for (map {$_->[0]} @{$prop->{uri}}, @{$prop->{system_id}}) {
    my $uri = $_;
    $uri =~ s/<>.*$//gs;
    $uri_to_entity->{$uri}->{$digest} = 1;
  }
  set_map (uri_to_entity => $uri_to_entity);

  my $pubid_to_entity = get_map ('pubid_to_entity');
  for (map {$_->[0]} @{$prop->{public_id}}) {
    my $pubid = $_;
    ## TODO: Is this normalization correct?
    $pubid =~ s/\s+/ /g;
    $pubid =~ s/^ //;
    $pubid =~ s/ $//;
    $pubid_to_entity->{$pubid}->{$digest} = 1;
  }
  set_map (pubid_to_entity => $pubid_to_entity);
} # update_maps

sub time_to_rfc3339 ($) {
  my @t = gmtime $_[0];
  return sprintf '%04d-%02d-%02d %02d:%02d:%02dZ',
      $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0];
} # time_to_rfc3339

sub http_to_rfc3339 ($) {
  if ($_[0] =~ /(\d+)\s*([A-Za-z]+)\s*(\d+)\s*(\d+):(\d+)(?>:(\d+))?\s*GMT/) {
    require Time::Local;
    my $t = Time::Local::timegm_nocheck
        ($6 || 0, $5, $4, $1,
         {jan => 0, feb => 1, mar => 1, apr => 1, may => 1,
          jun => 1, jul => 1, aug => 1, sep => 1, oct => 1,
          nov => 1, dec => 1}->{lc $2} || 0, $3);
    my @t = gmtime $t;
    return sprintf '%04d-%02d-%02d %02d:%02d:%02dZ',
        $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0];
  } else {
    return '';
  }
} # http_to_rfc3339

sub rfc3339_to_http ($) {
  if ($_[0] =~ /\A(\d+)-(\d+)-(\d+)[Tt ](\d+):(\d+)(?>:(\d+)(?>\.\d+)?)?(?>Z|([+-]\d+):(\d+))\z/) {
    require Time::Local;
    my $t = Time::Local::timegm_nocheck
        ($6 || 0, $5 - $8, $4 - $7, $3, $2 - 1, $1);
    my @t = gmtime $t;
    return sprintf '%02d %s %04d %02d:%02d:%02d GMT',
        $t[3], [qw(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec)]->[$t[4]],
        $t[5] + 1900, $t[2], $t[1], $t[0];
  } else {
    return '';
  }
} # rfc3339_to_http

sub get_remote_entity ($) {
  my $request_uri = $_[0];
  my $r = {};

    my $uri = Message::DOM::DOMImplementation->create_uri_reference
        ($request_uri);
    unless ({
             http => 1,
            }->{lc $uri->uri_scheme}) {
      return {uri => $request_uri, request_uri => $request_uri,
              error_status_text => 'URI scheme not allowed'};
    }

    require Message::Util::HostPermit;
    my $host_permit = new Message::Util::HostPermit;
    $host_permit->add_rule (<<EOH);
Allow host=suika port=80
Deny host=suika
Allow host=suika.fam.cx port=80
Deny host=suika.fam.cx
Deny host=localhost
Deny host=*.localdomain
Deny ipv4=0.0.0.0/8
Deny ipv4=10.0.0.0/8
Deny ipv4=127.0.0.0/8
Deny ipv4=169.254.0.0/16
Deny ipv4=172.0.0.0/11
Deny ipv4=192.0.2.0/24
Deny ipv4=192.88.99.0/24
Deny ipv4=192.168.0.0/16
Deny ipv4=198.18.0.0/15
Deny ipv4=224.0.0.0/4
Deny ipv4=255.255.255.255/32
Deny ipv6=0::0/0
Allow host=*
EOH
    unless ($host_permit->check ($uri->uri_host, $uri->uri_port || 80)) {
      return {uri => $request_uri, request_uri => $request_uri,
              error_status_text => 'Connection to the host is forbidden'};
    }

    require LWP::UserAgent;
    my $ua = WDCC::LWPUA->new;
    $ua->{wdcc_dom} = 'Message::DOM::DOMImplementation';
    $ua->{wdcc_host_permit} = $host_permit;
    $ua->agent ('Mozilla'); ## TODO: for now.
    $ua->parse_head (0);
    $ua->protocols_allowed ([qw/http/]);
    $ua->max_size (1000_000);
    my $req = HTTP::Request->new (GET => $request_uri);
    my $res = $ua->request ($req);
    ## TODO: 401 sets |is_success| true.
    if ($res->is_success) {
      $r->{base_uri} = $res->base; ## NOTE: It does check |Content-Base|, |Content-Location|, and <base>. ## TODO: Use our own code!
      $r->{uri} = $res->request->uri;
      $r->{request_uri} = $request_uri;

      ## TODO: More strict parsing...
      my $ct = $res->header ('Content-Type');
      if (defined $ct and $ct =~ m#^([0-9A-Za-z._+-]+/[0-9A-Za-z._+-]+)#) {
        $r->{media_type} = lc $1;
      }
      if (defined $ct and $ct =~ /;\s*charset\s*=\s*"?(\S+)"?/i) {
        $r->{charset} = lc $1;
        $r->{charset} =~ tr/\\//d;
      }

      $r->{s} = ''.$res->content;
    } else {
      $r->{uri} = $res->request->uri;
      $r->{request_uri} = $request_uri;
      $r->{error_status_text} = $res->status_line;
    }

    $r->{header_field} = [];
    $res->scan (sub {
      push @{$r->{header_field}}, [$_[0], $_[1]];
    });
    $r->{header_status_code} = $res->code;
    $r->{header_status_text} = $res->message;

  return $r;
} # get_remote_entity

package WDCC::LWPUA;
BEGIN { push our @ISA, 'LWP::UserAgent'; }

sub redirect_ok {
  my $ua = shift;
  unless ($ua->SUPER::redirect_ok (@_)) {
    return 0;
  }

  my $uris = $_[1]->header ('Location');
  return 0 unless $uris;
  my $uri = $ua->{wdcc_dom}->create_uri_reference ($uris);
  unless ({
           http => 1,
          }->{lc $uri->uri_scheme}) {
    return 0;
  }
  unless ($ua->{wdcc_host_permit}->check ($uri->uri_host, $uri->uri_port || 80)) {
    return 0;
  }
  return 1;
} # redirect_ok
